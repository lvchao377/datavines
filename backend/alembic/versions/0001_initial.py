"""create dv_* metadata tables"""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    from app.db import Base
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=op.get_bind())


def downgrade():
    from app.db import Base
    import app.models  # noqa: F401

    Base.metadata.drop_all(bind=op.get_bind())
