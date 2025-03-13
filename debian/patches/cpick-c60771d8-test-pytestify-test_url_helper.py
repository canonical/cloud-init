From c60771d8ef005154bacd5beb740949a7a830aeb1 Mon Sep 17 00:00:00 2001
From: James Falcon <james.falcon@canonical.com>
Date: Mon, 3 Mar 2025 08:33:41 -0600
Subject: [PATCH] test: pytestify test_url_helper.py
Bug: https://github.com/canonical/cloud-init/issues/6065
Bug-Ubuntu: https://bugs.launchpad.net/ubuntu/+source/cloud-init/+bug/2100963

---
 tests/unittests/test_url_helper.py | 59 ++++++++++++++----------------
 1 file changed, 27 insertions(+), 32 deletions(-)

--- a/tests/unittests/test_url_helper.py
+++ b/tests/unittests/test_url_helper.py
@@ -41,11 +41,9 @@ class TestOAuthHeaders(CiTestCase):
     def test_oauth_headers_raises_not_implemented_when_oathlib_missing(self):
         """oauth_headers raises a NotImplemented error when oauth absent."""
         with mock.patch.dict("sys.modules", {"oauthlib": None}):
-            with self.assertRaises(NotImplementedError) as context_manager:
+            with pytest.raises(NotImplementedError) as context_manager:
                 oauth_headers(1, 2, 3, 4, 5)
-        self.assertEqual(
-            "oauth support is not available", str(context_manager.exception)
-        )
+        assert "oauth support is not available" == str(context_manager.value)
 
     @skipIf(_missing_oauthlib_dep, "No python-oauthlib dependency")
     @mock.patch("oauthlib.oauth1.Client")
@@ -66,7 +64,7 @@ class TestOAuthHeaders(CiTestCase):
             "token_secret",
             "consumer_secret",
         )
-        self.assertEqual("url", return_value)
+        assert "url" == return_value
 
 
 class TestReadFileOrUrl(CiTestCase):
@@ -80,8 +78,8 @@ class TestReadFileOrUrl(CiTestCase):
         data = b"This is my file content\n"
         util.write_file(tmpf, data, omode="wb")
         result = read_file_or_url("file://%s" % tmpf)
-        self.assertEqual(result.contents, data)
-        self.assertEqual(str(result), data.decode("utf-8"))
+        assert result.contents == data
+        assert str(result) == data.decode("utf-8")
 
     @responses.activate
     def test_read_file_or_url_str_from_url(self):
@@ -91,8 +89,8 @@ class TestReadFileOrUrl(CiTestCase):
         data = b"This is my url content\n"
         responses.add(responses.GET, url, data)
         result = read_file_or_url(url)
-        self.assertEqual(result.contents, data)
-        self.assertEqual(str(result), data.decode("utf-8"))
+        assert result.contents == data
+        assert str(result) == data.decode("utf-8")
 
     @responses.activate
     def test_read_file_or_url_str_from_url_streamed(self):
@@ -103,8 +101,8 @@ class TestReadFileOrUrl(CiTestCase):
         responses.add(responses.GET, url, data)
         result = read_file_or_url(url, stream=True)
         assert isinstance(result, UrlResponse)
-        self.assertEqual(result.contents, data)
-        self.assertEqual(str(result), data.decode("utf-8"))
+        assert result.contents == data
+        assert str(result) == data.decode("utf-8")
 
     @responses.activate
     def test_read_file_or_url_str_from_url_redacting_headers_from_logs(self):
@@ -114,15 +112,15 @@ class TestReadFileOrUrl(CiTestCase):
 
         def _request_callback(request):
             for k in headers.keys():
-                self.assertEqual(headers[k], request.headers[k])
+                assert headers[k] == request.headers[k]
             return (200, request.headers, "does_not_matter")
 
         responses.add_callback(responses.GET, url, callback=_request_callback)
 
         read_file_or_url(url, headers=headers, headers_redact=["sensitive"])
         logs = self.logs.getvalue()
-        self.assertIn(REDACTED, logs)
-        self.assertNotIn("sekret", logs)
+        assert REDACTED in logs
+        assert "sekret" not in logs
 
     @responses.activate
     def test_read_file_or_url_str_from_url_redacts_noheaders(self):
@@ -132,15 +130,15 @@ class TestReadFileOrUrl(CiTestCase):
 
         def _request_callback(request):
             for k in headers.keys():
-                self.assertEqual(headers[k], request.headers[k])
+                assert headers[k] == request.headers[k]
             return (200, request.headers, "does_not_matter")
 
         responses.add_callback(responses.GET, url, callback=_request_callback)
 
         read_file_or_url(url, headers=headers)
         logs = self.logs.getvalue()
-        self.assertNotIn(REDACTED, logs)
-        self.assertIn("sekret", logs)
+        assert REDACTED not in logs
+        assert "sekret" in logs
 
     def test_wb_read_url_defaults_honored_by_read_file_or_url_callers(self):
         """Readurl param defaults used when unspecified by read_file_or_url
@@ -161,19 +159,16 @@ class TestReadFileOrUrl(CiTestCase):
         class FakeSession(requests.Session):
             @classmethod
             def request(cls, **kwargs):
-                self.assertEqual(
-                    {
-                        "url": url,
-                        "allow_redirects": True,
-                        "method": "GET",
-                        "headers": {
-                            "User-Agent": "Cloud-Init/%s"
-                            % (version.version_string())
-                        },
-                        "stream": False,
+                assert {
+                    "url": url,
+                    "allow_redirects": True,
+                    "method": "GET",
+                    "headers": {
+                        "User-Agent": "Cloud-Init/%s"
+                        % (version.version_string())
                     },
-                    kwargs,
-                )
+                    "stream": False,
+                } == kwargs
                 return m_response
 
         with mock.patch(M_PATH + "requests.Session") as m_session:
@@ -182,13 +177,13 @@ class TestReadFileOrUrl(CiTestCase):
                 FakeSession(),
             ]
             # assert no retries and check_status == True
-            with self.assertRaises(UrlError) as context_manager:
+            with pytest.raises(UrlError) as context_manager:
                 response = read_file_or_url(url)
-            self.assertEqual("broke", str(context_manager.exception))
+            assert "broke" == str(context_manager.value)
             # assert default headers, method, url and allow_redirects True
             # Success on 2nd call with FakeSession
             response = read_file_or_url(url)
-        self.assertEqual(m_response, response._response)
+        assert m_response == response._response
 
 
 class TestReadFileOrUrlParameters:
