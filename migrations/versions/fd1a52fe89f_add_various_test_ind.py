"""Add various TestCase indexes

Revision ID: fd1a52fe89f
Revises: 5177cfff57d7
Create Date: 2013-11-04 17:03:03.005904

"""

# revision identifiers, used by Alembic.
revision = 'fd1a52fe89f'
down_revision = '5177cfff57d7'

from alembic import op


def upgrade():
    # TestCase
    op.create_index('idx_test_project_id', 'test', ['project_id'])
    op.create_index('idx_test_suite_id', 'test', ['suite_id'])
    op.create_unique_constraint('unq_test_key', 'test', ['build_id', 'suite_id', 'label_sha'])


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    pass
    ### end Alembic commands ###
