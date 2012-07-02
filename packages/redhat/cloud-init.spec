%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

# See: See: http://www.zarb.org/~jasonc/macros.php
# Or: http://fedoraproject.org/wiki/Packaging:ScriptletSnippets
# Or: http://www.rpm.org/max-rpm/ch-rpm-inside.html

Name:           cloud-init
Version:        {{version}}
Release:        {{release}}%{?dist}
Summary:        Cloud instance init scripts

Group:          System Environment/Base
License:        GPLv3
URL:            http://launchpad.net/cloud-init

Source0:        {{archive_name}}
BuildArch:      noarch
BuildRoot:      %{_tmppath}

BuildRequires:        python-devel
BuildRequires:        python-setuptools

# System util packages needed
Requires:       shadow-utils
Requires:       rsyslog
Requires:       iproute
Requires:       e2fsprogs
Requires:       net-tools
Requires:       procps
Requires:       shadow-utils

# Install pypi 'dynamic' requirements
{{for r in requires}}
Requires:       {{r}}
{{endfor}}

{{if init_d}}
Requires(post):       chkconfig
Requires(postun):     initscripts
Requires(preun):      chkconfig
Requires(preun):      initscripts
{{endif}}

{{if systemd}}
BuildRequires:  systemd-units
Requires(post):   systemd-units
Requires(postun): systemd-units
Requires(preun):  systemd-units
{{endif}}

%description
Cloud-init is a set of init scripts for cloud instances.  Cloud instances
need special scripts to run during initialization to retrieve and install
ssh keys and to let the user run various scripts.

%prep
%setup -q -n %{name}-%{version}-{{revno}}

%build
%{__python} setup.py build

%install
rm -rf $RPM_BUILD_ROOT
%{__python} setup.py install -O1 --skip-build --root $RPM_BUILD_ROOT

# Note that /etc/rsyslog.d didn't exist by default until F15.
# el6 request: https://bugzilla.redhat.com/show_bug.cgi?id=740420
mkdir -p $RPM_BUILD_ROOT/%{_sysconfdir}/rsyslog.d
cp -p tools/21-cloudinit.conf \
                    $RPM_BUILD_ROOT/%{_sysconfdir}/rsyslog.d/21-cloudinit.conf

{{if init_d}}
mkdir -p $RPM_BUILD_ROOT/%{_initddir}/
{{endif}}
{{if init_d_local}}
cp -p initd/cloud-init-local $RPM_BUILD_ROOT/%{_initddir}/
cp -p initd/cloud-config $RPM_BUILD_ROOT/%{_initddir}/
cp -p initd/cloud-final $RPM_BUILD_ROOT/%{_initddir}/
{{elif init_d}}
cp -p initd/cloud-init $RPM_BUILD_ROOT/%{_initddir}/
cp -p initd/cloud-config $RPM_BUILD_ROOT/%{_initddir}/
cp -p initd/cloud-final $RPM_BUILD_ROOT/%{_initddir}/
{{endif}}

{{if systemd}}
mkdir -p        $RPM_BUILD_ROOT/%{_unitdir}
cp -p systemd/* $RPM_BUILD_ROOT/%{_unitdir}
{{endif}}

%clean
rm -rf $RPM_BUILD_ROOT

%post

{{if systemd}}
if [ $1 -eq 1 ]
then
    /bin/systemctl enable cloud-config.service     >/dev/null 2>&1 || :
    /bin/systemctl enable cloud-final.service      >/dev/null 2>&1 || :
    /bin/systemctl enable cloud-init.service       >/dev/null 2>&1 || :
    /bin/systemctl enable cloud-init-local.service >/dev/null 2>&1 || :
fi
{{endif}}

{{if init_d_local}}
/sbin/chkconfig --add /etc/rc.d/init.d/cloud-init-local
{{elif init_d}}
/sbin/chkconfig --add /etc/rc.d/init.d/cloud-init
{{endif}}
{{if init_d}}
/sbin/chkconfig --add /etc/rc.d/init.d/cloud-config
/sbin/chkconfig --add /etc/rc.d/init.d/cloud-final
{{endif}}

%preun

{{if init_d_local}}
if [ $1 -eq 0 ]
then
    /sbin/service cloud-init-local stop >/dev/null 2>&1
    /sbin/chkconfig --del cloud-init-local
fi
{{elif init_d}}
if [ $1 -eq 0 ]
then
    /sbin/service cloud-init stop >/dev/null 2>&1
    /sbin/chkconfig --del cloud-init
fi
{{endif}}
{{if init_d}}
if [ $1 -eq 0 ]
then
    /sbin/service cloud-config stop >/dev/null 2>&1
    /sbin/chkconfig --del cloud-config
    /sbin/service cloud-final stop >/dev/null 2>&1
    /sbin/chkconfig --del cloud-final
fi
{{endif}}

{{if systemd}}
if [ $1 -eq 0 ]
then
    /bin/systemctl --no-reload disable cloud-config.service >/dev/null 2>&1 || :
    /bin/systemctl --no-reload disable cloud-final.service  >/dev/null 2>&1 || :
    /bin/systemctl --no-reload disable cloud-init.service   >/dev/null 2>&1 || :
    /bin/systemctl --no-reload disable cloud-init-local.service >/dev/null 2>&1 || :
fi
{{endif}}

%postun

{{if systemd}}
/bin/systemctl daemon-reload >/dev/null 2>&1 || :
{{endif}}

%files

{{if init_d}}
%attr(0755, root, root) %{_initddir}/cloud-config
%attr(0755, root, root) %{_initddir}/cloud-final
{{endif}}
{{if init_d_local}}
%attr(0755, root, root) %{_initddir}/cloud-init-local
{{elif init_d}}
%attr(0755, root, root) %{_initddir}/cloud-init
{{endif}}

{{if systemd}}
%{_unitdir}/cloud-config.service
%{_unitdir}/cloud-config.target
%{_unitdir}/cloud-init.service
%{_unitdir}/cloud-init-local.service
%{_unitdir}/cloud-final.service
{{endif}}

# Program binaries
%{_bindir}/cloud-init*

# There doesn't seem to be an agreed upon place for these
# although it appears the standard says /usr/lib but rpmbuild
# will try /usr/lib64 ??
/usr/lib/%{name}/uncloud-init
/usr/lib/%{name}/write-ssh-key-fingerprints

# Docs
%doc TODO LICENSE ChangeLog Requires
%doc %{_defaultdocdir}/cloud-init/*

# Configs
%config(noreplace)      %{_sysconfdir}/cloud/cloud.cfg
%dir                    %{_sysconfdir}/cloud/cloud.cfg.d
%config(noreplace)      %{_sysconfdir}/cloud/cloud.cfg.d/*.cfg
%config(noreplace)      %{_sysconfdir}/cloud/cloud.cfg.d/README
%dir                    %{_sysconfdir}/cloud/templates
%config(noreplace)      %{_sysconfdir}/cloud/templates/*
%config(noreplace) %{_sysconfdir}/rsyslog.d/21-cloudinit.conf

# Python code is here...
%{python_sitelib}/*

%changelog

{{changelog}}
