"""Negative contract probes for config validation and retained bytes integrity."""
import unittest
from toolbox.cleaner import CleanerError,_coerce_by_schema,_strict_json_loads
from test_p2_gate import install_packs,bundle_ok,_fixture_raw,AS_OF,TOOL
from toolbox.cleaner import Cleaner
from pathlib import Path
import tempfile,copy

class StrictContract(unittest.TestCase):
 def test_boolean_is_not_numeric_enum(self):
  with self.assertRaises(CleanerError):_coerce_by_schema(False,{"enum":[0]},"enum")
 def test_object_required(self):
  with self.assertRaises(CleanerError):_coerce_by_schema({}, {"type":"object","required":["x"]},"object")
 def test_object_additional_properties(self):
  with self.assertRaises(CleanerError):_coerce_by_schema({"extra":1},{"type":"object","additionalProperties":False},"object")
 def test_string_pattern(self):
  with self.assertRaises(CleanerError):_coerce_by_schema("javascript:bad",{"type":"string","pattern":"^https://"},"url")
 def test_date_format(self):
  with self.assertRaises(CleanerError):_coerce_by_schema("last week",{"type":"string","format":"date-time"},"time")
 def test_unknown_schema_type(self):
  with self.assertRaises(CleanerError):_coerce_by_schema(1,{"type":"invented"},"type")
 def test_nonfinite_in_unmapped_metadata(self):
  with self.assertRaises(CleanerError):_strict_json_loads(b'{"metadata":{"unused":1e999}}')
 def test_retained_bytes_require_both_hashes(self):
  contract=install_packs(Path(tempfile.mkdtemp(prefix="p2-strict-")),"cuisines")
  for key in ("content_hash","source_hash"):
   raw=_fixture_raw(bundle_ok());raw.pop(key)
   with self.subTest(key=key),self.assertRaises(CleanerError):Cleaner(contract,as_of=AS_OF,tool_version=TOOL).clean(raw)
 def test_missing_pointer_schema_rejected(self):
  contract=install_packs(Path(tempfile.mkdtemp(prefix="p2-strict-")),"cuisines")
  contract.pointers["pointers"].pop("/draft/summary")
  with self.assertRaises(CleanerError):Cleaner(contract,as_of=AS_OF,tool_version=TOOL).clean(_fixture_raw(bundle_ok()))
 def test_evidence_original_revision_conflict_rejected(self):
  contract=install_packs(Path(tempfile.mkdtemp(prefix="p2-revision-")),"cuisines")
  for value in (None,True,1.0,"2",0,999):
   b=bundle_ok();b["candidates"][0]["evidence"][0]["source_record_revision"]=value
   with self.subTest(value=value),self.assertRaises(CleanerError):Cleaner(contract,as_of=AS_OF,tool_version=TOOL).clean(_fixture_raw(b))
 def test_original_metadata_survives(self):
  contract=install_packs(Path(tempfile.mkdtemp(prefix="p2-strict-")),"cuisines")
  b=bundle_ok();b["candidates"][0]["city_id"]="shanghai";b["candidates"][0]["feed_id"]="source-feed"
  row=Cleaner(contract,as_of=AS_OF,tool_version=TOOL).clean(_fixture_raw(b))[0]
  self.assertEqual(row["payload"]["metadata"],{"city_id":"shanghai","feed_id":"source-feed"})

if __name__=="__main__":unittest.main()
