"""baseline

Revision ID: 737fc545621b
Revises:
Create Date: 2026-10-04 15:40:08.612124

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "737fc545621b"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
