from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

engine_args = {
    "echo": settings.DEBUG,
}

if settings.DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}
else:
    engine_args.update({
        "pool_size": 20,
        "max_overflow": 10,
        "pool_pre_ping": True,
        "pool_recycle": 300,
    })

engine = create_async_engine(
    settings.DATABASE_URL,
    **engine_args
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    # Ensure all ORM models are imported so Base.metadata knows about all tables
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Check and add columns if they are missing
        from sqlalchemy import inspect, text
        def add_cols_if_missing(connection):
            insp = inspect(connection)
            # Resumes table columns
            if "resumes" in insp.get_table_names():
                columns = [c["name"] for c in insp.get_columns("resumes")]
                for col_name in ["research_papers", "achievements"]:
                    if col_name not in columns:
                        connection.execute(text(f"ALTER TABLE resumes ADD COLUMN {col_name} JSON"))
            
            # Users table columns
            if "users" in insp.get_table_names():
                u_cols = [c["name"] for c in insp.get_columns("users")]
                user_adds = [
                    ("college", "VARCHAR(255)"),
                    ("department", "VARCHAR(255)"),
                    ("course", "VARCHAR(255)"),
                    ("year", "INTEGER"),
                    ("skills", "JSON"),
                    ("must_change_password", "BOOLEAN DEFAULT FALSE"),
                    ("failed_login_attempts", "INTEGER DEFAULT 0"),
                    ("locked_until", "TIMESTAMP WITH TIME ZONE"),
                    ("last_login_at", "TIMESTAMP WITH TIME ZONE"),
                    ("last_login_ip", "VARCHAR(50)"),
                    ("two_factor_enabled", "BOOLEAN DEFAULT FALSE"),
                ]
                for col_name, col_type in user_adds:
                    if col_name not in u_cols:
                        connection.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))

            # Interviews table columns
            if "interviews" in insp.get_table_names():
                i_cols = [c["name"] for c in insp.get_columns("interviews")]
                if "coding_score" not in i_cols:
                    connection.execute(text("ALTER TABLE interviews ADD COLUMN coding_score FLOAT"))

            # Reports table columns
            if "reports" in insp.get_table_names():
                r_cols = [c["name"] for c in insp.get_columns("reports")]
                if "coding_score" not in r_cols:
                    connection.execute(text("ALTER TABLE reports ADD COLUMN coding_score FLOAT DEFAULT 0.0"))
                if "coding_breakdown" not in r_cols:
                    connection.execute(text("ALTER TABLE reports ADD COLUMN coding_breakdown JSON"))

        await conn.run_sync(add_cols_if_missing)

    # Seed Default Super Admin Account
    from sqlalchemy import select, func
    from app.models.user import User, UserRole
    from app.utils.security import hash_password

    async with async_session() as session:
        result = await session.execute(select(User).where(func.lower(User.email) == "vikky.code@gmail.com"))
        admin = result.scalar_one_or_none()
        if not admin:
            super_admin = User(
                email="vikky.code@gmail.com",
                hashed_password=hash_password("CodeZone@12"),
                full_name="Super Admin",
                role=UserRole.ADMIN,
                must_change_password=True,
                is_active=True,
                college="Platform HQ",
                department="Administration",
            )
            session.add(super_admin)
            await session.commit()


