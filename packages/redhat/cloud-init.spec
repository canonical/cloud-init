%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

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


{{for r in bd_requires}}
BuildRequires: {{r}}
{{endfor}}

# Install requirements
{{for r in requires}}
Requires: {{r}}
{{endfor}}

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

%clean
rm -rf $RPM_BUILD_ROOT

%files

# Docs
{{for r in docs}}
%doc {{r}}
{{endfor}}

# Configs
{{for r in configs}}
%config(noreplace) %{_sysconfdir}/{{r}}
{{endfor}}

# Other files
{{for r in files}}
{{r}}
{{endfor}}

# Python sitelib
%{python_sitelib}/*

%changelog

{{changelog}}
