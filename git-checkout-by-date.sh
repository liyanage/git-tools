#!/bin/sh
#
# git-checkout-by-date.sh 2012-03-09 Foo Bar Baz
#

set -e

BASEDIR=$PWD
DATESPEC="$1"
shift

for i in $*; do
	cd "$BASEDIR/$i"
	if [ $DATESPEC == master ]; then
		git co master
	else
		git co $(git rev-list -n1 --before="$DATESPEC" master)
	fi
done

cd "$BASEDIR"