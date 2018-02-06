from sqlalchemy.schema import CreateTable, DropTable
import pytest
import sqlalchemy as sa
from kant.eventstore import EventStream
from kant import aggregates, events
from kant.eventstore.connection import connect
from kant import projections
from kant.projections.sa import SQLAlchemyProjectionAdapter


class BankAccountCreated(events.EventModel):
    __empty_stream__ = True

    id = events.CUIDField(primary_key=True)
    owner = events.CharField()


class DepositPerformed(events.EventModel):
    amount = events.DecimalField()


class WithdrawalPerformed(events.EventModel):
    amount = events.DecimalField()


class BankAccount(aggregates.Aggregate):
    id = aggregates.IntegerField()
    owner = aggregates.CharField()
    balance = aggregates.IntegerField()

    def apply_bank_account_created(self, event):
        self.id = event.id
        self.owner = event.owner
        self.balance = 0

    def apply_deposit_performed(self, event):
        self.balance += event.amount


@pytest.fixture
async def eventstore(dbsession):
    eventstore = await connect(
        pool=dbsession,
    )
    await eventstore.create_keyspace('event_store')
    return eventstore


@pytest.fixture
async def metadata():
    return sa.MetaData()


@pytest.mark.asyncio
async def test_projection_should_create_projection(saconnection, eventstore, metadata):
    # arrange
    statement = sa.Table('statement', metadata,  # NOQA
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('owner', sa.String(255)),
        sa.Column('balance', sa.Integer),
    )
    await saconnection.execute(CreateTable(statement))

    class Statement(projections.Projection):
        __keyspace__ = 'event_store'
        id = projections.IntegerField()
        owner = projections.CharField()
        balance = projections.IntegerField()

        def when_bank_account_created(self, event):
            self.id = event.id
            self.owner = event.owner
            self.balance = 0

    # act
    projection_manager = SQLAlchemyProjectionAdapter(saconnection)
    projection_manager.register(statement, Statement)
    eventstore.projections.bind(projection_manager)

    bank_account = BankAccount()
    bank_account.dispatch(BankAccountCreated(
        id=123,
        owner='John Doe',
    ))
    async with eventstore.open('event_store/{}'.format(bank_account.id), 'w') as eventstream:
        eventstream += bank_account.get_events()
    # assert
    result = await saconnection.execute(statement.select())
    result = list(result)
    assert len(result) == 1
    assert result[0].id == 123
    assert result[0].owner == 'John Doe'
    assert result[0].balance == 0


@pytest.mark.asyncio
async def test_projection_should_update_projection(saconnection, eventstore, metadata):
    # arrange
    statement = sa.Table('statement', metadata,  # NOQA
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('owner', sa.String(255)),
        sa.Column('balance', sa.Integer),
    )
    await saconnection.execute(CreateTable(statement))

    class Statement(projections.Projection):
        __keyspace__ = 'event_store'
        id = projections.IntegerField()
        owner = projections.CharField()
        balance = projections.IntegerField()

        def when_bank_account_created(self, event):
            self.id = event.id
            self.owner = event.owner
            self.balance = 0

        def when_deposit_performed(self, event):
            self.balance += event.amount

    # act
    projection_manager = SQLAlchemyProjectionAdapter(saconnection)
    projection_manager.register(statement, Statement)
    eventstore.projections.bind(projection_manager)

    bank_account = BankAccount()
    bank_account.dispatch(BankAccountCreated(
        id=321,
        owner='John Doe',
    ))
    async with eventstore.open('event_store/{}'.format(bank_account.id), 'w') as eventstream:
        eventstream += bank_account.get_events()
        bank_account.clear_events()

    bank_account.dispatch(DepositPerformed(
        amount=20,
    ))
    bank_account.dispatch(DepositPerformed(
        amount=20,
    ))
    async with eventstore.open('event_store/{}'.format(bank_account.id), 'r') as eventstream:
        eventstream += bank_account.get_events()
    # assert
    result = await saconnection.execute(statement.select())
    result = list(result)
    assert len(result) == 1
    assert result[0].id == 321
    assert result[0].owner == 'John Doe'
    assert result[0].balance == 40
