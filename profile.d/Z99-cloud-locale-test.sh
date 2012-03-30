export FOO=bar
#!/bin/sh
# vi: ts=4 noexpandtab
#
# Author: Ben Howard <ben.howard@canonical.com>
# Author: Scott Moser <scott.moser@ubuntu.com>
# (c) 2012, Canonical Group, Ltd.
#
# Purpose: Detect invalid locale settings and inform the user
#  of how to fix them.
#

locale_warn() {
	local cr="
"
	local line bad_names="" bad_lcs="" key="" value="" var=""
	local w1 w2 w3 w4 remain
	# locale is expected to output either:
	# VARIABLE=
	# VARIABLE="value"
	# locale: Cannot set LC_SOMETHING to default locale
	while read -r w1 w2 w3 w4 remain; do
		case "$w1" in
			locale:) bad_names="${bad_names} ${w4}";;
			*)
				key=${w1%%=*}
				val=${w1#*=}
				val=${val#\"}
				val=${val%\"}
				vars="${vars} $key=$val";;
		esac
	done
	for bad in $bad_names; do
		for var in ${vars}; do
			[ "${bad}" = "${var%=*}" ] &&
				bad_lcs="${bad_lcs} ${var#*=}" && break 2
		done
	done
	bad_lcs=${bad_lcs# }
	[ -n "$bad_lcs" ] || return 0

	printf "_____________________________________________________________________\n"
	printf "WARNING! Your environment specifies an invalid locale.\n"
	printf " This can affect your user experience significantly, including the\n"
	printf " ability to manage packages. You may install the locales by running\n"
	printf " the following command(s):\n\n"

	local bad invalid="" to_gen="" sfile="/usr/share/i18n/SUPPORTED"
	if [ ! -e "$sfile" ]; then
		printf "  sudo apt-get install locales\n"
	fi
	if [ -e "$sfile" ]; then
		for bad in ${bad_lcs}; do
			grep -q -i "${bad}" "$sfile" &&
				to_gen="${to_gen} ${bad}" ||
				invalid="${invalid} ${bad}"
		done
	else
		to_gen=$bad_lcs
	fi

	for bad in ${to_gen}; do
		printf "   sudo apt-get install language-pack-${bad%%_*}\n"
		printf "   sudo locale-gen ${bad}\n"
	done
	printf "\n"
	for bad in ${invalid}; do
        	printf "WARNING: '${bad}' is an invalid locale\n"
	done

	printf "To see all available language packs, run:\n"
	printf "   apt-cache search \"^language-pack-*\"\n"
	printf "To see the current locale settings, run 'locale'\n"
	printf "This message can be disabled by running:\n"
	printf "    touch /var/lib/cloud/instance/locale.skip\n"
	printf "_____________________________________________________________________\n\n"
}

[ -f /var/lib/cloud/instance/locale.skip ] && return

locale_warn <<EOF
$(locale 2>&1)
EOF
unset locale_warn
