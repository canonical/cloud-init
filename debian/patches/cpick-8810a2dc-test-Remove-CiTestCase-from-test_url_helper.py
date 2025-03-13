From 8810a2dccf8502549f2498a96ad7ff379fa93b87 Mon Sep 17 00:00:00 2001
From: James Falcon <james.falcon@canonical.com>
Date: Mon, 3 Mar 2025 08:40:54 -0600
Subject: [PATCH] test: Remove CiTestCase from test_url_helper.py
Bug: https://github.com/canonical/cloud-init/issues/6065
Bug-Ubuntu: https://bugs.launchpad.net/ubuntu/+source/cloud-init/+bug/2100963

---
 tests/unittests/test_url_helper.py | 32 ++++++++++++++----------------
 1 file changed, 15 insertions(+), 17 deletions(-)

--- a/tests/unittests/test_url_helper.py
+++ b/tests/unittests/test_url_helper.py
@@ -2,6 +2,7 @@
 # pylint: disable=attribute-defined-outside-init
 
 import logging
+import pathlib
 from functools import partial
 from threading import Event
 from time import process_time
@@ -23,7 +24,7 @@ from cloudinit.url_helper import (
     readurl,
     wait_for_url,
 )
-from tests.unittests.helpers import CiTestCase, mock, skipIf
+from tests.unittests.helpers import mock, skipIf
 
 try:
     import oauthlib
@@ -37,7 +38,7 @@ except ImportError:
 M_PATH = "cloudinit.url_helper."
 
 
-class TestOAuthHeaders(CiTestCase):
+class TestOAuthHeaders:
     def test_oauth_headers_raises_not_implemented_when_oathlib_missing(self):
         """oauth_headers raises a NotImplemented error when oauth absent."""
         with mock.patch.dict("sys.modules", {"oauthlib": None}):
@@ -67,17 +68,14 @@ class TestOAuthHeaders(CiTestCase):
         assert "url" == return_value
 
 
-class TestReadFileOrUrl(CiTestCase):
-
-    with_logs = True
-
-    def test_read_file_or_url_str_from_file(self):
+class TestReadFileOrUrl:
+    def test_read_file_or_url_str_from_file(self, tmp_path: pathlib.Path):
         """Test that str(result.contents) on file is text version of contents.
         It should not be "b'data'", but just "'data'" """
-        tmpf = self.tmp_path("myfile1")
+        tmpf = tmp_path / "myfile1"
         data = b"This is my file content\n"
         util.write_file(tmpf, data, omode="wb")
-        result = read_file_or_url("file://%s" % tmpf)
+        result = read_file_or_url(f"file://{tmpf}")
         assert result.contents == data
         assert str(result) == data.decode("utf-8")
 
@@ -105,7 +103,9 @@ class TestReadFileOrUrl(CiTestCase):
         assert str(result) == data.decode("utf-8")
 
     @responses.activate
-    def test_read_file_or_url_str_from_url_redacting_headers_from_logs(self):
+    def test_read_file_or_url_str_from_url_redacting_headers_from_logs(
+        self, caplog
+    ):
         """Headers are redacted from logs but unredacted in requests."""
         url = "http://hostname/path"
         headers = {"sensitive": "sekret", "server": "blah"}
@@ -118,12 +118,11 @@ class TestReadFileOrUrl(CiTestCase):
         responses.add_callback(responses.GET, url, callback=_request_callback)
 
         read_file_or_url(url, headers=headers, headers_redact=["sensitive"])
-        logs = self.logs.getvalue()
-        assert REDACTED in logs
-        assert "sekret" not in logs
+        assert REDACTED in caplog.text
+        assert "sekret" not in caplog.text
 
     @responses.activate
-    def test_read_file_or_url_str_from_url_redacts_noheaders(self):
+    def test_read_file_or_url_str_from_url_redacts_noheaders(self, caplog):
         """When no headers_redact, header values are in logs and requests."""
         url = "http://hostname/path"
         headers = {"sensitive": "sekret", "server": "blah"}
@@ -136,9 +135,8 @@ class TestReadFileOrUrl(CiTestCase):
         responses.add_callback(responses.GET, url, callback=_request_callback)
 
         read_file_or_url(url, headers=headers)
-        logs = self.logs.getvalue()
-        assert REDACTED not in logs
-        assert "sekret" in logs
+        assert REDACTED not in caplog.text
+        assert "sekret" in caplog.text
 
     def test_wb_read_url_defaults_honored_by_read_file_or_url_callers(self):
         """Readurl param defaults used when unspecified by read_file_or_url
