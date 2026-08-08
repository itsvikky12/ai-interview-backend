from __future__ import annotations
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.interview import Interview
from app.models.question import Question
from app.models.response import Response
from app.models.report import Report
from app.models.user import User
from app.ai.response_evaluator import generate_interview_summary, is_no_answer
from app.services.skill_gap_service import SkillGapService
from app.services.storage_service import StorageService
from app.utils.logger import get_logger
import io
import json

logger = get_logger(__name__)


class ReportService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = StorageService()

    async def generate_report(self, interview_id: UUID) -> Report:
        return await self._process_and_save_report(interview_id)

    async def start_async_generation(self, interview_id: UUID, background_tasks) -> Report:
        result = await self.db.execute(select(Report).where(Report.interview_id == str(interview_id)))
        report = result.scalar_one_or_none()
        
        if report and report.pdf_url:
            return report
            
        # Fetch responses and questions to calculate instant scores
        res_result = await self.db.execute(
            select(Response, Question)
            .join(Question, Response.question_id == Question.id)
            .where(Response.interview_id == str(interview_id))
        )
        rows = res_result.all()

        tech_scores = []
        comm_scores = []
        hr_scores = []
        overall_scores = []
        
        for response, question in rows:
            is_pending = response.feedback in ("Pending evaluation...", "Evaluating...", "", None)
            if is_pending:
                if is_no_answer(response.answer_text):
                    score = 0.0
                elif len((response.answer_text or "").split()) < 10:
                    score = 3.0
                else:
                    score = 5.0
            else:
                score = response.score if response.score is not None else 0.0

            overall_scores.append(score)
            if question.question_type.value in ("technical", "system_design", "follow_up") or (5 <= question.order_index <= 19):
                tech_scores.append(score)
            if (20 <= question.order_index <= 24) or question.question_type.value in ("hr", "behavioral"):
                hr_scores.append(score)
            comm_scores.append(score)

        avg_tech = sum(tech_scores) / max(len(tech_scores), 1)
        avg_comm = sum(comm_scores) / max(len(comm_scores), 1)
        avg_hr = sum(hr_scores) / max(len(hr_scores), 1)
        avg_overall = sum(overall_scores) / max(len(overall_scores), 1)

        if not report:
            report = Report(
                interview_id=str(interview_id),
                technical_score=round(avg_tech, 2),
                communication_score=round(avg_comm, 2),
                confidence_score=round(avg_comm * 0.8, 2),
                overall_score=round(avg_overall, 2),
                strengths=[],
                weaknesses=[],
                skill_gaps={},
                improvement_roadmap=[],
                question_scores=[],
                summary="Your detailed report is being prepared in the background.",
                pdf_url=None
            )
            self.db.add(report)
            await self.db.flush()
        else:
            report.technical_score = round(avg_tech, 2)
            report.communication_score = round(avg_comm, 2)
            report.confidence_score = round(avg_comm * 0.8, 2)
            report.overall_score = round(avg_overall, 2)
            await self.db.flush()
            
        background_tasks.add_task(self._run_async_report_generation, interview_id)
        return report

    async def _run_async_report_generation(self, interview_id: UUID) -> None:
        from app.database import async_session
        try:
            async with async_session() as db:
                bg_service = ReportService(db)
                await bg_service._process_and_save_report(interview_id)
        except Exception as e:
            logger.error("background_report_task_failed", error=str(e), interview_id=str(interview_id))

    async def _process_and_save_report(self, interview_id: UUID) -> Report:
        result = await self.db.execute(select(Interview).where(Interview.id == str(interview_id)))
        interview = result.scalar_one_or_none()
        if not interview:
            raise ValueError("Interview not found")

        result = await self.db.execute(select(User).where(User.id == interview.user_id))
        user = result.scalar_one_or_none()

        # Fetch all responses with their questions
        result = await self.db.execute(
            select(Response, Question)
            .join(Question, Response.question_id == Question.id)
            .where(Response.interview_id == str(interview_id))
            .order_by(Question.order_index)
        )
        rows = result.all()

        # Evaluate and transcribe all responses in parallel on-demand
        import asyncio
        import base64
        from app.ai.openai_client import transcribe_audio
        from app.ai.response_evaluator import evaluate_response

        async def evaluate_single_row(response: Response, question: Question):
            # Only evaluate if the response is pending/evaluating
            if response.feedback in ("Pending evaluation...", "Evaluating...", ""):
                # 1. Transcribe audio if needed
                if response.answer_text.startswith("__AUDIO__:"):
                    try:
                        audio_b64 = response.answer_text.split("__AUDIO__:")[1]
                        audio_bytes = base64.b64decode(audio_b64)
                        transcription = await transcribe_audio(audio_bytes)
                        response.answer_text = transcription if transcription.strip() else "(Silence)"
                    except Exception as ex:
                        logger.error("report_transcribe_failed", error=str(ex))
                        response.answer_text = "(Failed to transcribe audio)"

                # Check if this answer was flagged as weak/incomplete or no answer!
                is_no_ans = is_no_answer(response.answer_text)
                is_weak = isinstance(response.weaknesses, list) and "candidate_response_incomplete_flag" in response.weaknesses

                # 2. Evaluate answer using GPT or handle no-answer
                try:
                    evaluation = await evaluate_response(
                        question=question.question_text,
                        question_type=question.question_type.value,
                        expected_keywords=question.expected_keywords.split(",") if question.expected_keywords else [],
                        difficulty=question.difficulty,
                        answer=response.answer_text,
                    )
                    if is_no_ans or evaluation["score"] == 0.0:
                        response.score = 0.0
                        response.feedback = evaluation.get("feedback", "No answer provided for this question.")
                        response.strengths = []
                        response.weaknesses = ["candidate_response_incomplete_flag", "No answer provided"]
                    elif is_weak:
                        response.score = min(3.0, float(evaluation.get("score", 3.0)))
                        response.feedback = f"Response was incomplete/brief. {evaluation.get('feedback', '')}"
                        response.strengths = []
                        response.weaknesses = ["candidate_response_incomplete_flag", "Incomplete or very brief answer"]
                    else:
                        response.score = evaluation["score"]
                        response.feedback = evaluation["feedback"]
                        response.strengths = evaluation["strengths"]
                        response.weaknesses = evaluation["weaknesses"]
                except Exception as ex:
                    logger.error("report_eval_failed", error=str(ex))
                    if is_no_ans:
                        response.score = 0.0
                        response.feedback = "No answer provided."
                        response.strengths = []
                        response.weaknesses = ["candidate_response_incomplete_flag", "No answer provided"]
                    elif is_weak:
                        response.score = 3.0
                        response.feedback = "Incomplete response. Fallback evaluation completed."
                        response.strengths = []
                        response.weaknesses = ["candidate_response_incomplete_flag"]
                    else:
                        response.score = 5.0
                        response.feedback = "Fallback evaluation completed."
                        response.strengths = []
                        response.weaknesses = []

        # Run all pending evaluations concurrently
        tasks = [evaluate_single_row(row[0], row[1]) for row in rows]
        await asyncio.gather(*tasks)
        await self.db.flush()

        question_scores = []
        tech_scores = []
        comm_scores = []
        hr_scores = []
        for response, question in rows:
            is_weak = isinstance(response.weaknesses, list) and "candidate_response_incomplete_flag" in response.weaknesses
            qs = {
                "question": question.question_text,
                "question_type": question.question_type.value,
                "topic": question.topic,
                "score": response.score or 0,
                "feedback": response.feedback or "",
                "strengths": response.strengths or [],
                "weaknesses": response.weaknesses or [],
                "student_answer": response.answer_text,
                "is_weak": is_weak,
            }
            question_scores.append(qs)
            if question.question_type.value in ("technical", "system_design", "follow_up") or (5 <= question.order_index <= 19):
                tech_scores.append(response.score or 0)
            if (20 <= question.order_index <= 24) or question.question_type.value in ("hr", "behavioral"):
                hr_scores.append(response.score or 0)
            comm_scores.append(response.score or 0)

        avg_tech = sum(tech_scores) / max(len(tech_scores), 1)
        avg_comm = sum(comm_scores) / max(len(comm_scores), 1)
        avg_hr = sum(hr_scores) / max(len(hr_scores), 1)
        avg_overall = sum(s["score"] for s in question_scores) / max(len(question_scores), 1)

        # Generate AI summary and Skill gap analysis concurrently
        skill_gap_service = SkillGapService(self.db)
        
        summary_task = generate_interview_summary(
            candidate_name=user.full_name if user else "Candidate",
            target_role=interview.target_role,
            question_scores=question_scores,
            avg_technical=avg_tech,
            avg_communication=avg_comm,
            speech_metrics=interview.speech_metrics,
            anti_cheat_flags=interview.anti_cheat_flags,
        )
        
        skill_gap_task = skill_gap_service.analyze(interview_id)
        
        summary_data, skill_gaps = await asyncio.gather(summary_task, skill_gap_task)

        confidence_score = interview.confidence_score or (avg_comm * 0.8)

        # Formulate structured combined summary text
        exec_sum = summary_data.get("executive_summary", "")
        tech_anal = summary_data.get("technical_analysis", "")
        comm_anal = summary_data.get("communication_analysis", "")
        hire_rec = summary_data.get("hire_recommendation", "Hire")
        
        combined_summary = (
            f"### Executive Summary\n{exec_sum}\n\n"
            f"### Technical Assessment\n{tech_anal}\n\n"
            f"### Communication Assessment\n{comm_anal}\n\n"
            f"### Hiring Recommendation\n**{hire_rec}**"
        )

        # Check if report exists, update or create
        result = await self.db.execute(select(Report).where(Report.interview_id == str(interview_id)))
        report = result.scalar_one_or_none()

        report_data = {
            "technical_score": round(avg_tech, 2),
            "communication_score": round(avg_comm, 2),
            "confidence_score": round(confidence_score, 2),
            "overall_score": round(avg_overall, 2),
            "strengths": summary_data.get("top_strengths", []),
            "weaknesses": summary_data.get("critical_improvements", []),
            "skill_gaps": skill_gaps,
            "improvement_roadmap": skill_gaps.get("improvement_roadmap", []),
            "question_scores": question_scores,
            "summary": combined_summary,
        }

        if report:
            for key, value in report_data.items():
                setattr(report, key, value)
        else:
            report = Report(interview_id=str(interview_id), **report_data)
            self.db.add(report)

        # Update interview scores
        interview.technical_score = report_data["technical_score"]
        interview.communication_score = report_data["communication_score"]
        interview.confidence_score = report_data["confidence_score"]
        interview.overall_score = report_data["overall_score"]
        interview.feedback_summary = report_data["summary"]

        await self.db.flush()
        await self.db.refresh(report)

        # Generate PDF
        try:
            pdf_bytes = await self._generate_pdf(report, user, interview, question_scores, summary_data)
            pdf_url = await self.storage.upload_file(pdf_bytes, f"report_{interview_id}.pdf", folder="reports")
            report.pdf_url = pdf_url
            await self.db.flush()
        except Exception as e:
            logger.error("pdf_generation_failed", error=str(e))

        await self.db.commit()

        logger.info("report_generated", interview_id=str(interview_id), overall_score=report.overall_score)
        return report

    async def get_report(self, interview_id: UUID) -> Report | None:
        result = await self.db.execute(select(Report).where(Report.interview_id == str(interview_id)))
        report = result.scalar_one_or_none()
        if not report:
            return None
            
        # If the report is still generating in the background, calculate live real-time scores
        # based on currently completed evaluations.
        if not report.pdf_url:
            res_result = await self.db.execute(
                select(Response, Question)
                .join(Question, Response.question_id == Question.id)
                .where(Response.interview_id == str(interview_id))
                .order_by(Question.order_index)
            )
            rows = res_result.all()
            
            question_scores = []
            tech_scores = []
            comm_scores = []
            hr_scores = []
            overall_scores = []
            
            for response, question in rows:
                is_weak = isinstance(response.weaknesses, list) and "candidate_response_incomplete_flag" in response.weaknesses
                is_pending = response.feedback in ("Pending evaluation...", "Evaluating...", "", None)
                
                # Dynamic scoring
                if is_pending:
                    if is_no_answer(response.answer_text):
                        score = 0.0
                    elif len((response.answer_text or "").split()) < 10:
                        score = 3.0
                    else:
                        score = 5.0
                else:
                    score = response.score if response.score is not None else 0.0
                    
                qs = {
                    "question": question.question_text,
                    "question_type": question.question_type.value,
                    "topic": question.topic,
                    "score": score,
                    "feedback": response.feedback or ("No answer provided." if is_no_answer(response.answer_text) else "Pending evaluation..."),
                    "strengths": response.strengths or [],
                    "weaknesses": response.weaknesses or [],
                    "student_answer": response.answer_text,
                    "is_weak": is_weak,
                }
                question_scores.append(qs)
                
                overall_scores.append(score)
                if question.question_type.value in ("technical", "system_design", "follow_up") or (5 <= question.order_index <= 19):
                    tech_scores.append(score)
                if (20 <= question.order_index <= 24) or question.question_type.value in ("hr", "behavioral"):
                    hr_scores.append(score)
                comm_scores.append(score)
                
            avg_tech = sum(tech_scores) / max(len(tech_scores), 1)
            avg_comm = sum(comm_scores) / max(len(comm_scores), 1)
            avg_hr = sum(hr_scores) / max(len(hr_scores), 1)
            avg_overall = sum(overall_scores) / max(len(overall_scores), 1)
            
            report.technical_score = round(avg_tech, 2)
            report.communication_score = round(avg_comm, 2)
            report.confidence_score = round(avg_comm * 0.8, 2)
            report.overall_score = round(avg_overall, 2)
            report.question_scores = question_scores
            
        return report

    async def _generate_pdf(self, report: Report, user, interview: Interview, question_scores: list[dict], summary_data: dict) -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.units import inch

        buffer = io.BytesIO()
        # Set 0.5 inch margins for optimal corporate layout spacing (36pt)
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()

        # Modern Corporate MNC Theme Palette
        c_primary = colors.HexColor("#0f172a")     # Deep slate navy
        c_secondary = colors.HexColor("#1d4ed8")   # Royal blue
        c_accent = colors.HexColor("#b45309")      # Amber gold
        c_dark = colors.HexColor("#1e293b")        # Charcoal text
        c_light = colors.HexColor("#f8fafc")       # Soft grey background
        c_red = colors.HexColor("#dc2626")         # Red alert
        c_green = colors.HexColor("#059669")       # Green check

        title_style = ParagraphStyle(
            "MNC_Title", 
            parent=styles["Heading1"], 
            fontSize=20, 
            spaceAfter=6, 
            textColor=c_primary,
            fontName="Helvetica-Bold"
        )
        subtitle_style = ParagraphStyle(
            "MNC_Subtitle", 
            parent=styles["Normal"], 
            fontSize=9, 
            spaceAfter=15, 
            textColor=colors.HexColor("#475569"),
            fontName="Helvetica-Bold"
        )
        heading_style = ParagraphStyle(
            "MNC_Heading", 
            parent=styles["Heading2"], 
            fontSize=11, 
            spaceBefore=10,
            spaceAfter=6, 
            textColor=c_secondary,
            fontName="Helvetica-Bold"
        )
        subheading_style = ParagraphStyle(
            "MNC_Subheading", 
            parent=styles["Normal"], 
            fontSize=9.5, 
            spaceBefore=5,
            spaceAfter=3, 
            textColor=c_primary,
            fontName="Helvetica-Bold"
        )
        body_style = ParagraphStyle(
            "MNC_Body", 
            parent=styles["Normal"], 
            fontSize=9, 
            spaceAfter=4, 
            leading=13,
            textColor=c_dark
        )

        elements = []

        # 1. Header
        elements.append(Paragraph("MNC TALENT ACQUISITION - CANDIDATE ASSESSMENT REPORT", title_style))
        elements.append(Paragraph("CONFIDENTIAL & PROPRIETARY | GENERATED VIA AI MOCK INTERVIEW PLATFORM", subtitle_style))

        # Divider line
        divider = Table([[""]], colWidths=[523], rowHeights=[2])
        divider.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), c_secondary),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
        ]))
        elements.append(divider)
        elements.append(Spacer(1, 10))

        # 2. Candidate Profile Grid
        duration_text = "N/A"
        if interview.started_at and interview.completed_at:
            dur = (interview.completed_at - interview.started_at).total_seconds() / 60
            duration_text = f"{dur:.0f} minutes"

        profile_data = [
            [
                Paragraph("<b>Candidate Name:</b>", body_style), 
                Paragraph(user.full_name if user else "N/A", body_style),
                Paragraph("<b>Target Role:</b>", body_style), 
                Paragraph(interview.target_role, body_style)
            ],
            [
                Paragraph("<b>Date:</b>", body_style), 
                Paragraph(interview.created_at.strftime("%B %d, %Y"), body_style),
                Paragraph("<b>Duration:</b>", body_style), 
                Paragraph(duration_text, body_style)
            ],
            [
                Paragraph("<b>Language:</b>", body_style), 
                Paragraph(interview.language.capitalize(), body_style),
                Paragraph("<b>Assessment System:</b>", body_style), 
                Paragraph("AI Mock Interview Engine v1.0", body_style)
            ]
        ]
        profile_table = Table(profile_data, colWidths=[110, 150, 110, 153])
        profile_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), c_light),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elements.append(profile_table)
        elements.append(Spacer(1, 12))

        # 3. Assessment Dashboard Table
        proj_score = 0.0
        project_q = next((qs for qs in question_scores if qs.get("topic") in ("Project Discussion", "Project Knowledge")), None)
        if project_q:
            proj_score = project_q.get("score", 0.0)
        elif len(question_scores) > 5:
            proj_score = question_scores[5].get("score", 0.0)
        else:
            proj_score = report.technical_score

        hr_scores = [qs.get("score", 0.0) for qs in question_scores if qs.get("question_type") in ("hr", "behavioral") or qs.get("topic") == "HR Round"]
        hr_score = sum(hr_scores) / max(len(hr_scores), 1) if hr_scores else report.communication_score

        overall_pct = report.overall_score * 10

        hire_rec = summary_data.get("hire_recommendation", "Hire")
        rec_color = c_green if "hire" in hire_rec.lower() else (c_accent if "borderline" in hire_rec.lower() else c_red)

        dashboard_data = [
            [
                Paragraph("<b>Technical Score</b>", body_style),
                Paragraph("<b>Communication Score</b>", body_style),
                Paragraph("<b>Confidence Score</b>", body_style),
                Paragraph("<b>Project Knowledge Score</b>", body_style)
            ],
            [
                Paragraph(f"<font size=11 color='{c_secondary.hexval()}'><b>{report.technical_score:.1f}</b></font><font size=7>/10</font>", body_style),
                Paragraph(f"<font size=11 color='{c_secondary.hexval()}'><b>{report.communication_score:.1f}</b></font><font size=7>/10</font>", body_style),
                Paragraph(f"<font size=11 color='{c_secondary.hexval()}'><b>{report.confidence_score:.1f}</b></font><font size=7>/10</font>", body_style),
                Paragraph(f"<font size=11 color='{c_secondary.hexval()}'><b>{proj_score:.1f}</b></font><font size=7>/10</font>", body_style)
            ],
            [
                Paragraph("<b>HR Round Score</b>", body_style),
                Paragraph("<b>Overall Score</b>", body_style),
                Paragraph("<b>Overall Percentage</b>", body_style),
                Paragraph("<b>Hiring Recommendation</b>", body_style)
            ],
            [
                Paragraph(f"<font size=11 color='{c_secondary.hexval()}'><b>{hr_score:.1f}</b></font><font size=7>/10</font>", body_style),
                Paragraph(f"<font size=11 color='{c_primary.hexval()}'><b>{report.overall_score:.1f}</b></font><font size=7>/10</font>", body_style),
                Paragraph(f"<font size=11 color='{c_primary.hexval()}'><b>{overall_pct:.1f}%</b></font>", body_style),
                Paragraph(f"<font size=9 color='{rec_color.hexval()}'><b>{hire_rec}</b></font>", body_style)
            ]
        ]
        dashboard_table = Table(dashboard_data, colWidths=[130, 130, 120, 143])
        dashboard_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#e2e8f0")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#94a3b8")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elements.append(Paragraph("EXECUTIVE ASSESSMENT DASHBOARD", heading_style))
        elements.append(dashboard_table)
        elements.append(Spacer(1, 12))

        # 4. Competency Assessments
        elements.append(Paragraph("COMPETENCY ASSESSMENT REPORT", heading_style))
        
        elements.append(Paragraph("Executive Summary", subheading_style))
        elements.append(Paragraph(summary_data.get("executive_summary", "No executive summary available."), body_style))
        
        elements.append(Paragraph("Technical & Algorithmic Competency Analysis", subheading_style))
        elements.append(Paragraph(summary_data.get("technical_analysis", "No technical analysis available."), body_style))
        
        elements.append(Paragraph("Communication & Behavioral Articulation Analysis", subheading_style))
        elements.append(Paragraph(summary_data.get("communication_analysis", "No communication analysis available."), body_style))
        elements.append(Spacer(1, 10))

        # 5. Strengths & Actionable Roadmaps
        strengths_list = report.strengths if isinstance(report.strengths, list) else summary_data.get("top_strengths", [])
        weaknesses_list = report.weaknesses if isinstance(report.weaknesses, list) else summary_data.get("critical_improvements", [])

        if strengths_list or weaknesses_list:
            sw_data = [
                [
                    Paragraph("<b>Key Demonstrated Strengths</b>", subheading_style),
                    Paragraph("<b>Critical Actionable Improvements</b>", subheading_style)
                ],
                [
                    Paragraph("".join(f"• {s}<br/><br/>" for s in strengths_list[:4]), body_style),
                    Paragraph("".join(f"• {w}<br/><br/>" for w in weaknesses_list[:4]), body_style)
                ]
            ]
            sw_table = Table(sw_data, colWidths=[255, 268])
            sw_table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("BACKGROUND", (0, 0), (-1, 0), c_light),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            elements.append(sw_table)
            elements.append(Spacer(1, 10))

        # 6. Detailed Question-by-Question breakdown
        if question_scores:
            elements.append(Paragraph("DETAILED TRANSCRIPT & PERFORMANCE ASSESSMENTS", heading_style))
            for i, qs in enumerate(question_scores, 1):
                is_weak = qs.get("is_weak", False)
                
                # Check for weak weaknesses or scores
                weaknesses_arr = qs.get("weaknesses", [])
                if isinstance(weaknesses_arr, list) and "candidate_response_incomplete_flag" in weaknesses_arr:
                    is_weak = True

                type_label = qs.get("question_type", "technical").upper()
                score_val = qs.get("score", 0)

                # Render header for each question
                q_header_text = f"<b>STAGE {i}: {qs.get('topic', 'Technical')}</b> ({type_label})"
                if is_weak:
                    q_header_text += f" <font color='{c_red.hexval()}'><b>[INCOMPLETE RESPONSE]</b></font>"

                elements.append(Paragraph(q_header_text, subheading_style))
                elements.append(Paragraph(f"<b>Question:</b> {qs.get('question', '')}", body_style))
                
                ans_text = qs.get("student_answer", "No answer recorded.")
                elements.append(Paragraph(f"<b>Candidate Spoken Answer:</b> <i>{ans_text}</i>", body_style))
                
                score_str = f"<font color='{c_secondary.hexval()}'><b>{score_val:.1f}/10</b></font>"
                if is_weak:
                    score_str += " (Penalized due to brevity)"

                elements.append(Paragraph(f"<b>Score:</b> {score_str}", body_style))
                elements.append(Paragraph(f"<b>Assessor Feedback:</b> {qs.get('feedback', '')}", body_style))
                elements.append(Spacer(1, 4))

        doc.build(elements)
        return buffer.getvalue()

    def _rating(self, score: float) -> str:
        if score >= 8.5:
            return "Exceptional"
        elif score >= 7.0:
            return "Strong"
        elif score >= 5.5:
            return "Satisfactory"
        elif score >= 4.0:
            return "Needs Improvement"
        else:
            return "Below Expectations"
