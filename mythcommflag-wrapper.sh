#!/bin/bash

# The is from https://www.mythtv.org/wiki/Script_-_RemoveCommercials
#
# place in /usr/bin/
# Version using mythutil for 0.25+ as it no longer needs mythexport: Only checked on Freesat HD but it should work with 
# Freeview HD if they have AC3 audio.  Changed ffmpeg to ffmpeg, as ffmpeg is deprecated. ffmpeg used the Audio Descriptive
# track without the ac3 adjustment. On my test this was audio+ AD but I am told that it could be nearly all silence so I 
# forced the use of the ac3 track.
# Edited version which assumes all freesat/freeview channels conform to the silent gap requirement. There is therefore no 
# need for a whitelist.
# Updated for 0.27 as mysql.txt no longer exists.

# Function to extract data from config.xml

Extract(){
Sourcefile=$1
Searchterm=$2
# $1 is filename, $2 is search item
Filterterm="<"$Searchterm">"
Result=`grep $Filterterm <$Sourcefile `
Result=`echo ${Result//$Filterterm/}`
Filterterm="</"$Searchterm">"
Result=`echo ${Result//$Filterterm/}`
echo $Result
}
#End Extract

# From <http://www.mythtv.org/wiki/Silence-detect.sh>

silence_detect() {
		local filename=$1
		
		TMPDIR=`mktemp -d /tmp/mythcommflag.XXXXXX` || exit 1		

		cd $TMPDIR
		touch `basename $filename`.touch
# Find out if ac3(HD)
	ffprobe -show_streams -select_streams a $filename | grep -E 'ac3|aac' >/dev/null
	if [ $? -eq 0 ];then # ac3 stream
# use ffmpeg to get stream location from stderr/stdout. Info is in stderr so it has to be piped to stdout to see it(2>&1).
# find the line with ac3 This has the format     Stream #m:n[0xhex]...............
	streamline=$(ffmpeg -hide_banner -i $filename 2>&1 | grep -E 'ac3|aac' | grep -v 'visual impaired')
# Now strip that line to leave m:n
# strip off leading characters
	stream1=${streamline#*#} # leaving m:n[0xhex]........
# we now strip the trailing characters 
	stream2=${stream1%[0x*} # gives m:n in stream2
# export ac3 audio in mp3 format
	ffmpeg -i $filename -map $stream2 -codec:a mp3 sound.mp3
	else ffmpeg -i $filename -acodec mp3 sound.mp3
	fi
	mp3splt -s -p $MP3SPLT_OPTS sound.mp3

	CUTLIST=`tail --lines=+3 mp3splt.log|sort -g |\
	       awk 'BEGIN{start=0;ORS=","}{if($2-start<'$MAXCOMMBREAKSECS')
	       {finish=$2} else {print int(start*25+1)"-"int(finish*25-25);
	       start=$1; finish=$2;}}END{print int(start*25+1)"-"9999999}'`
	echo "silence-detect has generated cutlist: $CUTLIST" >>$LOGFILE 

	echo "silence-detect(): CHANID=$CHANID, STARTTIME=$STARTTIME" >>$LOGFILE
# remove the temporary directory and its contents		
	rm -rf $TMPDIR
}
# End Silence detect		


use_comskip() {
	local filename=$1
		
	TMPDIR=`mktemp -d /tmp/mythcommflag.XXXXXX` || exit 1		

	cd $TMPDIR
	touch `basename $filename`.touch
	/usr/local/bin/comskip --ini=/usr/local/bin/cpruk.ini --output=$TMPDIR --output-filename=cutlist --ts $filename | tee -a $LOGFILE

	CUTLIST=`cat cutlist.txt | awk -e 'BEGIN{ORS=","} /[0-9]+\s+[0-9]+/ { print $1"-"$2 }'`
	echo "use-comskip has generated cutlist: $CUTLIST" >>$LOGFILE 

	echo "use-comskip(): CHANID=$CHANID, STARTTIME=$STARTTIME" >>$LOGFILE
# remove the temporary directory and its contents		
	cd -
	rm -rf $TMPDIR
}
# End comskip

# Main body
 
# edit/tune these #
# Allow ad breaks to be up to 400s long by coalescing non-silence
MAXCOMMBREAKSECS=400
# -80dB and minimum of 01.0s to be considered 'silent'
# Limited investigation has shown that the advert gap is about 2 secs and the between adverts
# gap about 1 sec
#MP3SPLT_OPTS="th=-70,min=0.15"
MP3SPLT_OPTS="th=-80,min=1.0"
#MP3SPLT_OPTS="th=-80,min=0.50"
#MP3SPLT_OPTS="th=-60,min=0.10"
# Log file
LOGFILE="/var/log/mythtv/mythcommflag.log"
# Save passed parameters
NOPARAM=$#
PARAMSTR=$*
MANFLAG=false
if [ $NOPARAM -eq 4 -a "$1" = "-j" -a "$3" = "-v" ]; then
	# this is a manual flag job
	JOB=$2
	MANFLAG=true
fi

echo "starting Run ukcommflag $date" >>$LOGFILE

exec 2>>$LOGFILE

# Copy commercial skiplist to cutlist automatically? 1=Enabled
#COPYTOCUTLIST=1
COPYTOCUTLIST=0

MYTHCFG=""
# Find config.xml in Ver 0.27 as mysql.txt no longer exists
if [ -e $HOME/.mythtv/config.xml ]; then
	MYTHCFG="$HOME/.mythtv/config.xml"
fi


if [ -e $MYTHCONFDIR/config.xml ]; then
	MYTHCFG="$MYTHCONFDIR/config.xml"
fi
if [ "$MYTHCFG" = "" ]; then
	echo "No config.xml found in $MYTHCONFDIR or $HOME/.mythtv - exiting!" >>$LOGFILE
	exit 1
fi

# DB username and password
MYTHHOST=$(Extract $MYTHCFG "Host")
MYTHUSER=$(Extract $MYTHCFG "UserName")
MYTHPASS=$(Extract $MYTHCFG "Password")
export SSHPASS="${MYTHPASS}"
MYTHDB=$(Extract $MYTHCFG "DatabaseName")
# echo "Host, Username, Password, and Database name extracted" >>$LOGFILE
# echo $MYTHHOST"   "$MYTHUSER"   "$MYTHPASS"   "$MYTHDB >>$LOGFILE

# root of MythTV recordings
RECORDINGSROOT=`sshpass -e mysql -h${MYTHHOST} -u${MYTHUSER} -p -e "select dirname from storagegroup where groupname in ('Default', 'LiveTV');" $MYTHDB | tail -n +2 | sort | uniq | tr '\n' ' '`


echo "$0 run with [$PARAMSTR] at `date` by `whoami`" >>$LOGFILE
echo "RECORDINGSROOT=$RECORDINGSROOT" >>$LOGFILE


if [ $NOPARAM -eq 0 ]; then
	# run with no parameters, flag every unflagged recording
	exec mythcommflag
	exit $?
else
	if [ $MANFLAG != "true" ]; then
	# we're being used in some other way, run the real mythcommmflag
		exec mythcommflag $PARAMSTR
		exit $?
fi
echo "running job $JOB" >>$LOGFILE
#HASCUTLIST=`sshpass -e mysql -h${MYTHHOST} -u${MYTHUSER} -p -e "select recorded.cutlist from recorded join jobqueue where jobqueue.id=$JOB and jobqueue.chanid=recorded.chanid and jobqueue.starttime=recorded.starttime;" $MYTHDB | tail -n +2`	
#if [ "$HASCUTLIST" = "1" ]; then
#	echo "program already has (manual?) cutlist, exiting" >>$LOGFILE
#	exit 0
#fi
CALLSIGN=`sshpass -e mysql -h${MYTHHOST} -u${MYTHUSER} -p -e "select channel.callsign from channel join jobqueue where jobqueue.id=$JOB and jobqueue.chanid=channel.chanid;" $MYTHDB | tail -n +2`
CHANID=`sshpass -e mysql -h${MYTHHOST} -u${MYTHUSER} -p -e "select chanid from jobqueue where jobqueue.id=$JOB;" $MYTHDB | tail -n +2`	
STARTTIME=`sshpass -e mysql -h${MYTHHOST} -u${MYTHUSER} -p -e "select starttime from jobqueue where jobqueue.id=$JOB;" $MYTHDB | tail -n +2`
echo "channel callsign is $CALLSIGN" >>$LOGFILE
echo "chanid=$CHANID STARTTIME=$STARTTIME" >>$LOGFILE
BASENAME=`sshpass -e mysql -h${MYTHHOST} -u${MYTHUSER} -p -e "select recorded.basename from recorded join jobqueue where jobqueue.id=$JOB and jobqueue.chanid=recorded.chanid and jobqueue.starttime=recorded.starttime;" $MYTHDB | tail -n +2`	
echo "basename is $BASENAME" >>$LOGFILE
FILENAME=`ionice -c 3 nice find ${RECORDINGSROOT} -name $BASENAME`
echo "filename is $FILENAME" >>$LOGFILE


	# make lower case and remove white space to account for minor 
	# presentation changes between transmissions and over time callsigns
	# on Freesat and freeview differ e.g. "FIVE *" and "Five*". Also 
	# removed is the +1 suffix from the criteria, if the primary channel
	# is allowable the +1 variant should also be included in white list.
        # Remove HD on the same logic as +1
        # Convert to lower case
lowerCALLSIGN="$(echo $CALLSIGN | tr '[A-Z]' '[a-z]')"
        # Remove +1
lowerCALLSIGN=`echo ${lowerCALLSIGN//+1/}`
	# Remove +24
lowerCALLSIGN=`echo ${lowerCALLSIGN//+24/}`
	#Remove hd
lowerCALLSIGN=`echo ${lowerCALLSIGN//hd/}`
	#Remove spaces
lowerCALLSIGN="$(echo $lowerCALLSIGN | tr -d '[:space:]')"
     case $lowerCALLSIGN in
	# the following list should be in lower case and without any white space and no need to specify "+1" or HD variants
	# E4/channel 4 treats trailers as program. The silence markers are 
	# only either side of actual adverts. E4 often has trailers before and
	# after adverts, which will not be cut, and appear within the wanted show. 
	# Works for other FIVE channels with caveat that they include news 
	# bulletins which are't cut
	#"five"|"5"|"fiveusa"|"5usa"|"channel4"|"channel4hd"|"more4"|"e4"|"film4"|"4seven"|"itv1"|"itv1hd"|"itv2"|"itv3"|"itv4"|"dave"|"davejavu")
	"xxx"|"yyy")
	# A Blacklisted channel for com_skip
	echo "Callsign $CALLSIGN on Blacklist - will use silence_detect" >>$LOGFILE
	METHOD=silence_detect
	;;
	*)
        echo "Callsign $CALLSIGN not in Blacklist - will run use_comskip" >>$LOGFILE
	METHOD=use_comskip
        ;;		
     esac		

    sshpass -e mysql -h${MYTHHOST} -u${MYTHUSER} -p -e "update recorded set commflagged=2 where chanid=$CHANID and starttime='${STARTTIME}';" $MYTHDB
    CUTLIST=""
    if [ $METHOD == "use_comskip" ]; then
	    use_comskip $FILENAME
    else
	    silence_detect $FILENAME
    fi
    echo "${METHOD}() set CUTLIST to $CUTLIST" >>$LOGFILE
    let BREAKS=`grep -o "-" <<< "$CUTLIST" | wc -l`
    echo "$BREAKS break(s) found." >>$LOGFILE
    mythutil --setskiplist $CUTLIST --chanid="$CHANID" --starttime="${STARTTIME}"
    RC=$?
    echo "mythutil setskiplist returned $RC" >>$LOGFILE
    if [ $RC -eq 0 ]; then
	sshpass -e mysql -h${MYTHHOST} -u${MYTHUSER} -p -e "update recorded set commflagged=1 where chanid=$CHANID and starttime='${STARTTIME}';" ${MYTHDB}
	sshpass -e mysql -h${MYTHHOST} -u${MYTHUSER} -p -e "update jobqueue set status=272, comment='Finished, $BREAKS break(s) found.' where id=$JOB;" ${MYTHDB}			
	if [ $COPYTOCUTLIST -eq 1 ]; then
	    mythutil --gencutlist --chanid="$CHANID" --starttime="${STARTTIME}"
	    RC=$?
	    if [ $RC -eq 0 ]; then
		    echo "mythutil --gencutlist successfully copied skip list to cut list" >>$LOGFILE
	    else
		    echo "mythutil --gencutlist failed, returned $RC" >>$LOGFILE
	    fi
	fi			
    else
	echo "mythcommflag failed; returned $RC" >>$LOGFILE
	sshpass -e mysql -h${MYTHHOST} -u${MYTHUSER} -p -e "update recorded set commflagged=0 where chanid=$CHANID and starttime='${STARTTIME}';" ${MYTHDB}
    fi
fi
echo "Run Complete" >>$LOGFILE
