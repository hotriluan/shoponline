"""Recorded SAP steps, registered into the worker's TRANSACTIONS when this package is imported."""

from shoponline.sapjobs import queue
from shoponline.saprobot.transactions import read_zrsd001, read_zrsd004
from shoponline.saprobot.worker import TRANSACTIONS, Transaction

TRANSACTIONS.update(
    {
        queue.READ_ZRSD001: Transaction(read_zrsd001.run, writes=False),
        queue.READ_ZRSD004: Transaction(read_zrsd004.run, writes=False),
    }
)
