#!/bin/bash

DIR="$( cd "$( dirname "$0" )" && pwd )"
start_omx=$1

let i=1
while [ 1 ]; do
	if [[ ! -f ${DIR}/p2ptv-pi.pid ]]; then
		break
	elif [[ -z `ps -p $(cat ${DIR}/p2ptv-pi.pid) | tail -n +2` ]] ; then
		stop_playing
		break
	else
		${start_omx}
	fi
	let i++
	sleep 1
done
