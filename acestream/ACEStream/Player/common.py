#Embedded file name: ACEStream\Player\common.pyo


def get_status_msgs(ds, videoplayer_mediastate, appname, said_start_playback, decodeprogress, totalhelping, totalspeed):
    intime = 'Not playing for quite some time.'
    ETA = ((900, 'Playing in less than 15 minutes.'),
     (600, 'Playing in less than 10 minutes.'),
     (300, 'Playing in less than 5 minutes.'),
     (60, 'Playing in less than a minute.'))
    topmsg = ''
    msg = ''
    logmsgs = ds.get_log_messages()
    logmsg = None
    if len(logmsgs) > 0:
        logmsg = logmsgs[-1][1]
    preprogress = ds.get_vod_prebuffering_progress()
    playable = ds.get_vod_playable()
    t = ds.get_vod_playable_after()
    intime = ETA[0][1]
    for eta_time, eta_msg in ETA:
        if t > eta_time:
            break
        intime = eta_msg

    if ds.get_status() == DLSTATUS_HASHCHECKING:
        genprogress = ds.get_progress()
        pstr = str(int(genprogress * 100))
        msg = 'Checking already downloaded parts ' + pstr + '% done'
    elif ds.get_status() == DLSTATUS_STOPPED_ON_ERROR:
        msg = 'Error playing: ' + str(ds.get_error())
    elif ds.get_progress() == 1.0:
        msg = ''
    elif playable:
        if not said_start_playback:
            msg = 'Starting playback...'
        if videoplayer_mediastate == MEDIASTATE_STOPPED and said_start_playback:
            if totalhelping == 0:
                topmsg = u'Please leave the ' + appname + ' running, this will help other ' + appname + ' users to download faster.'
            else:
                topmsg = u'Helping ' + str(totalhelping) + ' ' + appname + ' users to download. Please leave it running in the background.'
            msg = ''
        elif videoplayer_mediastate == MEDIASTATE_PLAYING:
            said_start_playback = True
            topmsg = ''
            decodeprogress += 1
            msg = ''
        elif videoplayer_mediastate == MEDIASTATE_PAUSED:
            msg = 'Buffering... ' + str(int(100.0 * preprogress)) + '%'
        else:
            msg = ''
    elif preprogress != 1.0:
        pstr = str(int(preprogress * 100))
        npeers = ds.get_num_peers()
        npeerstr = str(npeers)
        if npeers == 0 and logmsg is not None:
            msg = logmsg
        elif npeers == 1:
            msg = 'Prebuffering ' + pstr + '% done (connected to 1 stream)'
        else:
            msg = 'Prebuffering ' + pstr + '% done (connected to ' + npeerstr + ' streams)'
    else:
        minutes = int(t / 60)
        if minutes < 1:
            start_time = 'in less than one minute'
        elif minutes == 1:
            start_time = 'in one minute'
        elif minutes < 10:
            start_time = 'in ' + str(minutes) + ' minutes'
        else:
            if minutes < 20:
                precision = 2
            elif minutes < 40:
                precision = 5
            elif minutes < 60:
                precision = 10
            else:
                precision = 15
            minutes = precision * int(round(minutes / precision))
            if minutes > 120:
                start_time = 'soon'
            else:
                start_time = 'in ' + str(minutes) + ' minutes'
        msg = 'Playback will start ' + start_time
    return [topmsg,
     msg,
     said_start_playback,
     decodeprogress]
