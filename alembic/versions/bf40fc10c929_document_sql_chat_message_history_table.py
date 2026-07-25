"""document sql chat message history table

Revision ID: bf40fc10c929
Revises:
Create Date: 2026-07-25 10:48:48.306744

No-op migration. `SQLChatMessageHistory` (used by `src/agent/memory.py`, no
`table_name` override) creates and manages its own table automatically on
first use — it is not created by this or any migration. This revision exists
only to document that table's shape as of this migration, as the starting
point for the migration chain, per issue #36: Alembic is being introduced
now, ahead of any schema it needs to own, so the tooling is proven before the
next real schema need (session metadata, document metadata) arrives.

Table `message_store` (default `table_name`, see
`langchain_community.chat_message_histories.sql.create_message_model`):

    id          INTEGER     PRIMARY KEY
    session_id  TEXT
    message     TEXT        -- JSON-serialized BaseMessage (message_to_dict)

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bf40fc10c929"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: message_store is created and managed by SQLChatMessageHistory itself."""
    pass


def downgrade() -> None:
    """No-op: nothing was created by upgrade()."""
    pass
