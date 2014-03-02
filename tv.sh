#!/bin/bash

PRG=$0
VERSION="p2ptv-pi v2.1"
number_regex='^[0-9]+$'
DIR="$( cd "$( dirname "$0" )" && pwd )"

let i=0
while read line || [[ -n "${line}" ]]; do ((++i))
	[[ "$line" =~ ^#.*$ ]] && continue
	TIPOS_CANAL[$i]=`echo ${line} | cut -d ";" -f1 | tr 'a-z' 'A-Z'`
    CANALES[$i]=`echo ${line} | cut -d ";" -f2`
	ENLACES[$i]=`echo ${line} | cut -d ";" -f3`
done < "${DIR}/canales.txt"
usage()
{
	echo "${VERSION}"
	echo ""
	echo "Uso: ${PRG} [OPCIONES]"
	echo ""
	echo "Opciones:"
	echo " -h			Muestra este menú"
	echo " -v			Muestra la versión"
	echo " -s			Apaga OMXPlayer y cierra la conexión P2P TV"
	echo " -l			Lista de todos los canales preconfigurados"
	echo " -c [CANAL]		Indica el canal a cargar (ver formatos admitidos)"
	echo " -o			Apaga XBMC e inicia OMXPlayer"
	echo ""
	echo "Formatos admitidos para [CANAL]:"
	echo " - Código de canal de uno de los canales preconfigurados (opción -l). Ejemplo: ./tv.sh -c 1"
        echo " - Enlace completo de Sopcast. Ejemplo: ./tv.sh -c sop://broker.sopcast.com:3912/150577"
        echo " - Enlace completo de AceStream. Ejemplo: ./tv.sh -c acestream://ff6d068d982f5ac218d164cf43f97dc39926cf55"
}

stop_playing()
{
	if [[ -f /var/run/p2ptv-pi.pid ]]; then
		kill -9 $(cat /var/run/p2ptv-pi.pid) > /dev/null 2>&1
		rm -f /var/run/p2ptv-pi.pid
	fi
	kill -2 $(pidof -x omxplayer.bin) > /dev/null 2>&1
	listening=1
	while [ -n "${listening}" ]; do
		listening=`netstat -na | grep 6878 | grep LISTEN | tail -1`
		sleep 1
	done
}

get_sopcast_link()
{
	wget $1 -O ${DIR}/page.html -o /dev/null
	sopcast_link_tmp=`grep "sop://" ${DIR}/page.html | tail -1 | awk 'BEGIN {FS="sop://"} {print $2}' | cut -d " " -f1`
	rm -f ${DIR}/page.html
	if ! [[ ${sopcast_link: -1} =~ ${number_regex} ]]; then
		sopcast_link_tmp=${sopcast_link_tmp%?}
	fi
	sopcast_link="sop://${sopcast_link_tmp}"
	echo "${sopcast_link}"
}

list_channels()
{
	printf "ID\tCanal\n"
	for i in "${!CANALES[@]}"; do 
		printf "%s\t%s\n" "$i" "${CANALES[$i]}"
	done
}

[[ $# -lt 1 ]] && usage && exit 1

while getopts ":hvsloc:" OPTION
do
	case "$OPTION" in
		h)
			usage
			exit 1
			;;
		v)
			echo "${VERSION}"
			exit 1
			;;
		s)
			stop_playing
			echo "Reproducción detenida"
			exit 1
			;;
		l)
			list_channels
			exit 1
			;;
		o)
			OMXPLAYER=1;
			;;
		c)
			CANAL=${OPTARG}
			;;
		?)
			usage
			exit 1
			;;
	esac
done

if [[ ${CANAL} == sop://* ]]; then
	ENLACE_P2P=${CANAL}
	ENLACE_OMXPLAYER="http://127.0.0.1:6878"
	TEXTO="Cargando canal Sopcast ${ENLACE_P2P}..."
	NOMBRE_CANAL=${CANAL}
elif [[ ${CANAL} == acestream://* ]]; then
	ENLACE_P2P=${CANAL}
	ENLACE_OMXPLAYER=`echo ${ENLACE_P2P} | awk 'BEGIN {FS="acestream://"} {print "http://127.0.0.1:6878/LOAD/PID="$2}'`
	TEXTO="Cargando canal AceStream ${ENLACE_P2P}..."
	NOMBRE_CANAL=${CANAL}
elif [[ ${CANAL} =~ ${number_regex} ]] && [[ -n ${ENLACES[${CANAL}]} ]] && [[ "${TIPOS_CANAL[${CANAL}]}" == "SOPCAST" ]]; then
	if [[ ${ENLACES[${CANAL}]} == sop://* ]]; then
		ENLACE_P2P=${ENLACES[${CANAL}]}
		ENLACE_OMXPLAYER="http://127.0.0.1:6878"
		TEXTO="Cargando canal Sopcast ${CANALES[${CANAL}]} (${ENLACE_P2P})..."
		NOMBRE_CANAL=${CANALES[${CANAL}]}
	elif [[ ${ENLACES[${CANAL}]} == http* ]]; then
		ENLACE_P2P=`get_sopcast_link ${ENLACES[${CANAL}]}`
		ENLACE_OMXPLAYER="http://127.0.0.1:6878"
		TEXTO="Cargando canal Sopcast ${CANALES[${CANAL}]} (${ENLACE_P2P})..."
		NOMBRE_CANAL=${CANALES[${CANAL}]}
	fi
elif [[ "${TIPOS_CANAL[${CANAL}]}" == "ACESTREAM" ]]; then
	ENLACE_P2P=${ENLACES[${CANAL}]}
	ENLACE_OMXPLAYER=`echo ${ENLACE_P2P} | awk 'BEGIN {FS="acestream://"} {print "http://127.0.0.1:6878/LOAD/PID="$2}'`
	TEXTO="Cargando canal AceStream ${CANALES[${CANAL}]} (${ENLACE_P2P})..."
	NOMBRE_CANAL=${CANALES[${CANAL}]}	
else
	usage
	exit 1
fi

stop_playing
echo "${TEXTO}"
if [[ "${TIPOS_CANAL[${CANAL}]}" == "SOPCAST" ]]; then
	${DIR}/sopcast/qemu-i386 ${DIR}/sopcast/lib/ld-linux.so.2 --library-path ${DIR}/sopcast/lib ${DIR}/sopcast/sp-sc-auth ${ENLACE_P2P} 1234 6878 > /dev/null 2>&1 & echo $! > /var/run/p2ptv-pi.pid
elif [[ "${TIPOS_CANAL[${CANAL}]}" == "ACESTREAM" ]]; then
	${DIR}/acestream/start.py > /dev/null 2>&1 & echo $! > /var/run/p2ptv-pi.pid
	sleep 20
fi

let timeout=0
while [ ${timeout} -lt 30 ]; do ((++i))
	listening=`netstat -na | grep 6878 | grep LISTEN | tail -1`
	if [[ "${TIPOS_CANAL[${CANAL}]}" == "SOPCAST" ]]; then
		process=`ps aux | grep qemu-i386 | grep -v grep`
	elif [[ "${TIPOS_CANAL[${CANAL}]}" == "ACESTREAM" ]]; then
		process=`ps aux | grep "acestream/start.py" | grep -v grep`
	fi
	if [ -n "${listening}" ] || [ -z "${process}" ]; then
		break
	else
		sleep 1
	fi
done

if [ -z "${listening}" ]; then
	echo "Imposible conectar al canal especificado"
	stop_playing
	exit 1
else
	echo "Conectado al canal ${NOMBRE_CANAL}"
fi

if [[ ${OMXPLAYER} -eq 1 ]]; then
	if ps ax | grep -v grep | grep xbmc > /dev/null; then
		echo "Apagando XBMC..."
		/etc/init.d/xbmc stop
	fi
	echo "Iniciando OMXPlayer..."
	omxplayer -r --live ${ENLACE_OMXPLAYER} > /dev/null 2>&1 &
fi

exit 0
