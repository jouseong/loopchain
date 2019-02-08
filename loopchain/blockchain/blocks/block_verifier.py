import hashlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable
from secp256k1 import PrivateKey, PublicKey
from .. import ExternalAddress, BlockVersionNotMatch, TransactionVerifier

if TYPE_CHECKING:
    from . import Block, BlockHeader
    from .. import TransactionVersioner


class BlockVerifier(ABC):
    version = None
    _ecdsa = PrivateKey()

    def __init__(self, tx_versioner: 'TransactionVersioner'):
        self._tx_versioner = tx_versioner
        self.invoke_func: Callable[['Block'], ('Block', dict)] = None

    def verify(self, block: 'Block', prev_block: 'Block', blockchain=None, generator: 'ExternalAddress'=None):
        self.verify_transactions(block, blockchain)
        return self.verify_common(block, prev_block, generator)

    def verify_loosely(self, block: 'Block', prev_block: 'Block', blockchain=None, generator: 'ExternalAddress'=None):
        self.verify_transactions_loosely(block, blockchain)
        return self.verify_common(block, prev_block, generator)

    def verify_common(self, block: 'Block', prev_block: 'Block', generator: 'ExternalAddress'=None):
        header: BlockHeader = block.header

        if header.timestamp is None:
            raise RuntimeError(f"Block({header.height}, {header.hash.hex()} does not have timestamp.")

        if header.height > 0 and header.prev_hash is None:
            raise RuntimeError(f"Block({header.height}, {header.hash.hex()} does not have prev_hash.")

        self.verify_version(block)

        if block.header.height > 0:
            self.verify_signature(block)

        if prev_block:
            self.verify_prev_block(block, prev_block)

        self._verify_common(block, prev_block, generator)

    @abstractmethod
    def _verify_common(self, block: 'Block', prev_block: 'Block', generator: 'ExternalAddress'=None):
        raise NotImplementedError

    def verify_transactions(self, block: 'Block', blockchain=None):
        for tx in block.body.transactions.values():
            tv = TransactionVerifier.new(tx.version, self._tx_versioner)
            tv.verify(tx, blockchain)

    def verify_transactions_loosely(self, block: 'Block', blockchain=None):
        for tx in block.body.transactions.values():
            tv = TransactionVerifier.new(tx.version, self._tx_versioner)
            tv.verify_loosely(tx, blockchain)

    def verify_version(self, block: 'Block'):
        if block.header.version != self.version:
            raise BlockVersionNotMatch(block.header.version, self.version,
                                       f"The block version is incorrect. Block({block.header})")

    def verify_prev_block(self, block: 'Block', prev_block: 'Block'):
        if block.header.prev_hash != prev_block.header.hash:
            raise RuntimeError(f"Block({block.header.height}, {block.header.hash.hex()}, "
                               f"PrevHash({block.header.prev_hash.hex()}), "
                               f"Expected({prev_block.header.hash.hex()}).")

        if block.header.height != prev_block.header.height + 1:
            raise RuntimeError(f"Block({block.header.height}, {block.header.hash.hex()}, "
                               f"Height({block.header.height}), "
                               f"Expected({prev_block.header.height + 1}).")

    def verify_signature(self, block: 'Block'):
        recoverable_sig = self._ecdsa.ecdsa_recoverable_deserialize(
            block.header.signature.signature(),
            block.header.signature.recover_id())
        raw_public_key = self._ecdsa.ecdsa_recover(block.header.hash,
                                                   recover_sig=recoverable_sig,
                                                   raw=True,
                                                   digest=hashlib.sha3_256)

        public_key = PublicKey(raw_public_key, ctx=self._ecdsa.ctx)
        hash_pub = hashlib.sha3_256(public_key.serialize(compressed=False)[1:]).digest()
        expect_address = hash_pub[-20:]
        if expect_address != block.header.peer_id:
            raise RuntimeError(f"block peer id {block.header.peer_id.hex_xx()}, "
                               f"expected {ExternalAddress(expect_address).hex_xx()}")

    @classmethod
    def new(cls, version: str, tx_versioner: 'TransactionVersioner') -> 'BlockVerifier':
        from . import v0_1a, v0_2, v0_3
        if version == v0_1a.version:
            return v0_1a.BlockVerifier(tx_versioner)

        if version == v0_2.version:
            return v0_2.BlockVerifier(tx_versioner)

        if version == v0_3.version:
            return v0_3.BlockVerifier(tx_versioner)

        raise NotImplementedError(f"BlockBuilder Version({version}) not supported.")

