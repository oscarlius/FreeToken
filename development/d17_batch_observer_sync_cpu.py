"""Verify the preintegrated D16 observer in the dedicated D17 tree, without a tag."""
from pathlib import Path
import d16_batch_observer_sync_cpu as sync

if __name__ == '__main__':
    sync.TREE = Path(__file__).resolve().parent / 'e2base1'
    sync.PARENT = '2396728f5f210b98bfde0b8ba3556e9cbc2b234f'
    sync.INVOKER_SOURCE = Path(__file__).read_bytes()
    sync.main()
