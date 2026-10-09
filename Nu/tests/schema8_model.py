import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Nu/tools'))
from schema8_model import convert


class ConversionTests(unittest.TestCase):
    def source(self, root, schema=7):
        payload=bytes(64*4+8192*64*2+64*2)
        checksum=14695981039346656037
        for byte in payload:checksum=((checksum^byte)*1099511628211)&((1<<64)-1)
        source=root/'source.nnue'
        source.write_bytes(struct.pack('<8sIIIIQ',b'NUNNUE1\0',schema,8192,64,256,checksum)+payload)
        return source,hashlib.sha256(source.read_bytes()).hexdigest()

    def test_preserves_payload_and_rejects_overwrite(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'Nu/work') as directory:
            root=Path(directory);source,pin=self.source(root);output=root/'eight.nnue'
            result=convert(source,output,pin)
            self.assertTrue(result['payload_unchanged'])
            self.assertEqual(source.read_bytes()[32:],output.read_bytes()[32:])
            self.assertEqual(struct.unpack_from('<I',source.read_bytes(),8)[0],7)
            self.assertEqual(struct.unpack_from('<I',output.read_bytes(),8)[0],8)
            with self.assertRaisesRegex(RuntimeError,'overwrite'):convert(source,output,pin)

    def test_corruption_pin_and_wrong_schema(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'Nu/work') as directory:
            root=Path(directory);source,pin=self.source(root);output=root/'eight.nnue'
            with self.assertRaisesRegex(RuntimeError,'pinned'):convert(source,output,'wrong')
            raw=bytearray(source.read_bytes());raw[-1]^=1;source.write_bytes(raw)
            with self.assertRaisesRegex(RuntimeError,'payload checksum'):convert(source,output,hashlib.sha256(raw).hexdigest())
            source,pin=self.source(root,6)
            with self.assertRaisesRegex(RuntimeError,'schema 7'):convert(source,output,pin)
            self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
