From d4566b1aa35951e6c32da330e627c023785026ea Mon Sep 17 00:00:00 2001
From: Dave Jones <dave.jones@canonical.com>
Date: Fri, 3 Apr 2026 02:31:16 +0100
Subject: [PATCH] fix(ubuntu): Configure arm64 to use archive.ubuntu.com
 (#6826)

Fixes GH-6825
LP: #2147101
---
 config/cloud.cfg.tmpl | 4 ++--
 1 file changed, 2 insertions(+), 2 deletions(-)

--- a/config/cloud.cfg.tmpl
+++ b/config/cloud.cfg.tmpl
@@ -359,7 +359,7 @@ system_info:
         security: https://deb.debian.org/debian-security
 {% elif variant in ["ubuntu", "unknown"] %}
   package_mirrors:
-    - arches: [i386, amd64]
+    - arches: [arm64, i386, amd64]
       failsafe:
         primary: http://archive.ubuntu.com/ubuntu
         security: http://security.ubuntu.com/ubuntu
@@ -369,7 +369,7 @@ system_info:
           - http://%(availability_zone)s.clouds.archive.ubuntu.com/ubuntu/
           - http://%(region)s.clouds.archive.ubuntu.com/ubuntu/
         security: []
-    - arches: [arm64, armel, armhf]
+    - arches: [armel, armhf]
       failsafe:
         primary: http://ports.ubuntu.com/ubuntu-ports
         security: http://ports.ubuntu.com/ubuntu-ports
