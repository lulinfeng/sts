#!/bin/sh
### BEGIN INIT INFO
# Provides:             sts
# Required-Start:       $remote_fs $syslog
# Required-Stop:        $remote_fs $syslog
# Default-Start:        2 3 4 5
# Default-Stop:
# Short-Description:    stress client
### END INIT INFO

# chkconfig: 2345 99 99
# description: stress client
# processname: sts


ROOT=$(dirname $(dirname $(readlink -f $0)))
PYPATH=${ROOT}/cli.py

if [ -f "$PYPATH" ]; then
	python ${PYPATH} $1
	exit 0
fi
