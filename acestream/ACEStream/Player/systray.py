#Embedded file name: ACEStream\Player\systray.pyo
import sys
import os
import textwrap
import time
import wx
from ACEStream.version import VERSION
from ACEStream.Core.BitTornado.clock import clock
from ACEStream.Core.API import *
from ACEStream.Plugin.defs import *
from ACEStream.Core.debug import DebugState
from ACEStream.Core.Utilities.logger import log, log_exc
BUTTON_ID_CLEAR_CACHE = 348
DEBUG = False
DEBUG_PIECES = False
DEBUG_VIDEOSTATUS = False
DEBUG_PROXY_BUF = False
DEBUG_LIVE_BUFFER_TIME = True
DEBUG_LIVE = False
SHOW_DEBUG_LEVEL = False

class PlayerTaskBarIcon(wx.TaskBarIcon):

    def __init__(self, wxapp, bgapp, iconfilename):
        wx.TaskBarIcon.__init__(self)
        self.bgapp = bgapp
        self.wxapp = wxapp
        self.icons = wx.IconBundle()
        self.icon = wx.Icon(iconfilename, wx.BITMAP_TYPE_ICO)
        self.icons.AddIcon(self.icon)
        self.Bind(wx.EVT_TASKBAR_LEFT_UP, self.OnLeftClicked)
        if sys.platform != 'darwin':
            self.SetIcon(self.icon, self.bgapp.appname)
        else:
            menuBar = wx.MenuBar()
            filemenu = wx.Menu()
            item = filemenu.Append(-1, 'E&xit', 'Terminate the program')
            self.Bind(wx.EVT_MENU, self.OnExit, item)
            wx.App.SetMacExitMenuItemId(item.GetId())

    def OnExit(self, e):
        self.wxapp.ExitMainLoop()

    def CreatePopupMenu(self):
        menu = wx.Menu()
        mi = menu.Append(wx.ID_ANY, self.bgapp.utility.lang.get('options_etc'))
        self.Bind(wx.EVT_MENU, self.OnOptions, id=mi.GetId())
        menu.AppendSeparator()
        if self.bgapp.user_profile is not None:
            mi = menu.Append(wx.ID_ANY, self.bgapp.utility.lang.get('user_profile'))
            self.Bind(wx.EVT_MENU, self.OnUserProfile, id=mi.GetId())
            menu.AppendSeparator()
        mi = menu.Append(wx.ID_ANY, self.bgapp.utility.lang.get('create_stream'))
        self.Bind(wx.EVT_MENU, self.OnStream, id=mi.GetId())
        menu.AppendSeparator()
        if DEBUG:
            mi = menu.Append(wx.ID_ANY, 'Statistics')
            self.Bind(wx.EVT_MENU, self.OnStat, id=mi.GetId())
            menu.AppendSeparator()
        if DEBUG_LIVE:
            mi = menu.Append(wx.ID_ANY, 'Live')
            self.Bind(wx.EVT_MENU, self.OnLive, id=mi.GetId())
            menu.AppendSeparator()
        mi = menu.Append(wx.ID_ANY, self.bgapp.utility.lang.get('menuexit'))
        self.Bind(wx.EVT_MENU, self.OnExitClient, id=mi.GetId())
        return menu

    def OnOptions(self, event = None):
        dlg = PlayerOptionsDialog(self.bgapp, self.icons)
        ret = dlg.ShowModal()
        dlg.Destroy()

    def OnUserProfile(self, event = None):
        dlg = UserProfileDialog(self.bgapp, self.icons)
        ret = dlg.ShowModal()
        dlg.Destroy()

    def OnStat(self, event = None):
        frame = StatFrame(self.bgapp, 'Statistics')
        frame.Show()

    def OnLive(self, event = None):
        frame = LiveFrame(self.bgapp, 'Live')
        frame.Show()

    def OnExitClient(self, event = None):
        self.wxapp.ExitMainLoop()

    def set_icon_tooltip(self, txt):
        if sys.platform == 'darwin':
            return
        self.SetIcon(self.icon, txt)

    def OnLeftClicked(self, event = None):
        if DEBUG:
            import webbrowser
            url = 'http://127.0.0.1:' + str(self.bgapp.httpport) + URLPATH_WEBIF_PREFIX
            webbrowser.open_new_tab(url)

    def OnStream(self, event = None):
        import webbrowser
        url = 'http://127.0.0.1:' + str(self.bgapp.httpport) + URLPATH_WEBIF_PREFIX + '/createstream'
        webbrowser.open_new_tab(url)


class StatFrame(wx.Frame):

    def __init__(self, bgapp, title):
        wx.Frame.__init__(self, None, title=title, pos=(50, 10), size=(1100, 450))
        self.bgapp = bgapp
        self.spewwait = clock()
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.SetBackgroundColour(wx.Colour(255, 255, 255))
        fw = 12
        spewList = wx.ListCtrl(self, pos=(0, 0), size=(1000, 300), style=wx.LC_REPORT | wx.LC_HRULES | wx.LC_VRULES)
        spewList.InsertColumn(0, 'Optimistic Unchoke', format=wx.LIST_FORMAT_CENTER, width=fw * 2)
        spewList.InsertColumn(1, 'Peer ID', width=0)
        spewList.InsertColumn(2, 'IP', width=fw * 11)
        spewList.InsertColumn(3, 'Local/Remote', format=wx.LIST_FORMAT_CENTER, width=fw * 2)
        spewList.InsertColumn(4, 'Up', format=wx.LIST_FORMAT_RIGHT, width=fw * 2)
        spewList.InsertColumn(5, 'Interested', format=wx.LIST_FORMAT_CENTER, width=fw * 2)
        spewList.InsertColumn(6, 'Choking', format=wx.LIST_FORMAT_CENTER, width=fw * 2)
        spewList.InsertColumn(7, 'Down', format=wx.LIST_FORMAT_RIGHT, width=fw * 8)
        spewList.InsertColumn(8, 'Interesting', format=wx.LIST_FORMAT_CENTER, width=fw * 2)
        spewList.InsertColumn(9, 'Choked', format=wx.LIST_FORMAT_CENTER, width=fw * 2)
        spewList.InsertColumn(10, 'Snubbed', format=wx.LIST_FORMAT_CENTER, width=fw * 2)
        spewList.InsertColumn(11, 'Downloaded', format=wx.LIST_FORMAT_RIGHT, width=fw * 5)
        spewList.InsertColumn(12, 'Uploaded', format=wx.LIST_FORMAT_RIGHT, width=fw * 5)
        spewList.InsertColumn(13, 'Completed', format=wx.LIST_FORMAT_RIGHT, width=fw * 6)
        spewList.InsertColumn(14, 'Peer Download Speed', format=wx.LIST_FORMAT_RIGHT, width=fw * 10)
        spewList.InsertColumn(15, 'Requested Piece', format=wx.LIST_FORMAT_CENTER, width=fw * 6)
        spewList.InsertColumn(16, 'Received Piece', format=wx.LIST_FORMAT_CENTER, width=fw * 6)
        self.spewList = spewList
        labelVOD = wx.StaticText(self, -1, 'static text')
        self.labelVOD = labelVOD
        gridSizer = wx.FlexGridSizer(cols=1, vgap=5)
        gridSizer.Add(spewList, -1, wx.EXPAND)
        gridSizer.Add(labelVOD, -1, wx.EXPAND)
        self.SetSizer(gridSizer)
        self.bgapp.statFrame = self

    def OnClose(self, event = None):
        self.bgapp.statFrame = None
        self.Destroy()

    def updateStats(self, spew, statistics = None, vod_stats = None):
        if spew is not None and clock() - self.spewwait > 1:
            self.spewwait = clock()
            spewList = self.spewList
            spewlen = len(spew) + 2
            if statistics is not None:
                kickbanlen = len(statistics.peers_kicked) + len(statistics.peers_banned)
                if kickbanlen:
                    spewlen += kickbanlen + 1
            else:
                kickbanlen = 0
            for x in range(spewlen - spewList.GetItemCount()):
                i = wx.ListItem()
                spewList.InsertItem(i)

            for x in range(spewlen, spewList.GetItemCount()):
                spewList.DeleteItem(len(spew) + 1)

            tot_uprate = 0.0
            tot_downrate = 0.0
            tot_downloaded = 0
            for x in range(len(spew)):
                if spew[x]['optimistic'] == 1:
                    a = '*'
                else:
                    a = ' '
                spewList.SetStringItem(x, 0, a)
                spewList.SetStringItem(x, 1, spew[x]['id'])
                spewList.SetStringItem(x, 2, spew[x]['ip'])
                spewList.SetStringItem(x, 3, spew[x]['direction'])
                if spew[x]['uprate'] > 100:
                    spewList.SetStringItem(x, 4, '%.0f kB/s' % (float(spew[x]['uprate']) / 1000))
                else:
                    spewList.SetStringItem(x, 4, ' ')
                tot_uprate += spew[x]['uprate']
                if spew[x]['uinterested'] == 1:
                    a = '*'
                else:
                    a = ' '
                spewList.SetStringItem(x, 5, a)
                if spew[x]['uchoked'] == 1:
                    a = '*'
                else:
                    a = ' '
                spewList.SetStringItem(x, 6, a)
                bitrate = None
                if vod_stats['videostatus'] is not None:
                    bitrate = vod_stats['videostatus'].bitrate
                if spew[x]['downrate'] > 100:
                    str_downrate = '%.0f' % (spew[x]['downrate'] / 1024.0)
                    if 'short_downrate' in spew[x]:
                        if bitrate is None:
                            str_downrate += ' (%.0f)' % (spew[x]['short_downrate'] / 1024 / 0.0)
                        else:
                            str_downrate += ' (%.0f, %.1f)' % (spew[x]['short_downrate'] / 1024.0, spew[x]['short_downrate'] / float(bitrate))
                    spewList.SetStringItem(x, 7, str_downrate)
                else:
                    spewList.SetStringItem(x, 7, ' ')
                tot_downrate += spew[x]['downrate']
                if spew[x]['dinterested'] == 1:
                    a = '*'
                else:
                    a = ' '
                spewList.SetStringItem(x, 8, a)
                if spew[x]['dchoked'] == 1:
                    a = '*'
                else:
                    a = ' '
                spewList.SetStringItem(x, 9, a)
                if spew[x]['snubbed'] == 1:
                    a = '*'
                else:
                    a = ' '
                spewList.SetStringItem(x, 10, a)
                tot_downloaded += spew[x]['dtotal']
                spewList.SetStringItem(x, 11, '%.2f MiB' % (float(spew[x]['dtotal']) / 1048576))
                if spew[x]['utotal'] is not None:
                    a = '%.2f MiB' % (float(spew[x]['utotal']) / 1048576)
                else:
                    a = ''
                spewList.SetStringItem(x, 12, a)
                spewList.SetStringItem(x, 13, '%.1f%%' % (float(int(spew[x]['completed'] * 1000)) / 10))
                if spew[x]['speed'] is not None:
                    a = '%.0f' % (float(spew[x]['speed']) / 1024)
                    if 'speed_proxy' in spew[x]:
                        a += ' | p:%.0f' % (float(spew[x]['speed_proxy']) / 1024)
                    if 'speed_non_proxy' in spew[x]:
                        a += ' | r:%.0f' % (float(spew[x]['speed_non_proxy']) / 1024)
                else:
                    a = ''
                spewList.SetStringItem(x, 14, a)
                spewList.SetStringItem(x, 15, str(spew[x]['last_requested_piece']))
                spewList.SetStringItem(x, 16, str(spew[x]['last_received_piece']))

            x = len(spew)
            for i in range(17):
                spewList.SetStringItem(x, i, '')

            x += 1
            spewList.SetStringItem(x, 2, '         TOTALS:')
            spewList.SetStringItem(x, 4, '%.0f kB/s' % (float(tot_uprate) / 1024))
            spewList.SetStringItem(x, 7, '%.0f kB/s' % (float(tot_downrate) / 1024))
            spewList.SetStringItem(x, 11, '%.2f MiB' % (float(tot_downloaded) / 1048576))
            spewList.SetStringItem(x, 12, '')
            for i in [0,
             1,
             3,
             5,
             6,
             8,
             9,
             10,
             13,
             14,
             15,
             16]:
                spewList.SetStringItem(x, i, '')

            if kickbanlen:
                x += 1
                for i in range(17):
                    spewList.SetStringItem(x, i, '')

                for peer in statistics.peers_kicked:
                    x += 1
                    spewList.SetStringItem(x, 2, peer[0])
                    spewList.SetStringItem(x, 1, peer[1])
                    spewList.SetStringItem(x, 4, 'KICKED')
                    for i in [0,
                     3,
                     5,
                     6,
                     7,
                     8,
                     9,
                     10,
                     11,
                     12,
                     13,
                     14,
                     15,
                     16,
                     17]:
                        spewList.SetStringItem(x, i, '')

                for peer in statistics.peers_banned:
                    x += 1
                    spewList.SetStringItem(x, 2, peer[0])
                    spewList.SetStringItem(x, 1, peer[1])
                    spewList.SetStringItem(x, 4, 'BANNED')
                    for i in [0,
                     3,
                     5,
                     6,
                     7,
                     8,
                     9,
                     10,
                     11,
                     12,
                     13,
                     14,
                     15,
                     16,
                     17]:
                        spewList.SetStringItem(x, i, '')

            if vod_stats is not None:
                info = ''
                if DEBUG_PROXY_BUF:
                    for pos, data in vod_stats['proxybuf'].iteritems():
                        length = len(data)
                        info += str(pos) + ' '
                        for i in xrange(length / 131072):
                            info += '-'

                        info += str(pos + length - 1) + '\n'

                    info += 'buf: ' + str(vod_stats['outbuf']) + '\n'
                if DEBUG_VIDEOSTATUS:
                    if vod_stats['videostatus'] is not None:
                        vs = vod_stats['videostatus']
                        info += ' >> idx: ' + str(vs.fileindex)
                        info += ', br: ' + str(vs.bitrate / 1024)
                        info += ', len: ' + str(vs.piecelen / 1024)
                        info += ', first: ' + str(vs.first_piece)
                        info += ', last: ' + str(vs.last_piece)
                        info += ', have: ' + str(vs.numhave)
                        info += ', comp: %.2f' % vs.completed
                        info += ', prebuf: ' + str(vs.prebuffering)
                        info += ', pos: ' + str(vs.playback_pos)
                        info += ', hp: ' + str(vs.prebuf_high_priority_pieces)
                        info += ', pp: ' + str(vs.prebuf_missing_pieces)
                        have = vs.have[:]
                        have.sort()
                        info += ', pieces: ' + str(have)
                    for vs in vod_stats['extra_videostatus']:
                        info += '\n   index: ' + str(vs.fileindex)
                        info += ', first piece: ' + str(vs.first_piece)
                        info += ', last piece: ' + str(vs.last_piece)
                        info += ', numhave: ' + str(vs.numhave)
                        info += ', completed: %.2f' % vs.completed
                        info += ', prebuf: ' + str(vs.prebuffering)
                        info += ', hp: ' + str(vs.prebuf_high_priority_pieces)
                        info += ', pp: ' + str(vs.prebuf_missing_pieces)
                        have = vs.have[:]
                        have.sort()
                        info += ', pieces: ' + str(have)

                if DEBUG_PIECES:
                    if statistics is not None:
                        for piece in xrange(len(statistics.storage_inactive_list)):
                            inactive = statistics.storage_inactive_list[piece]
                            if inactive is None:
                                inactive = 'all'
                            elif inactive == 1:
                                inactive = 'none'
                            else:
                                inactive = str(len(inactive))
                            info += '\n' + str(piece) + ': inactive=' + inactive + ' active=' + str(statistics.storage_active_list[piece]) + ' dirty=' + str(statistics.storage_dirty_list[piece])

                self.labelVOD.SetLabel(info)


class LiveFrame(wx.Frame):

    def __init__(self, bgapp, title):
        wx.Frame.__init__(self, None, title=title, pos=(50, 10), size=(1100, 450))
        self.bgapp = bgapp
        self.clock = clock()
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.SetBackgroundColour(wx.Colour(255, 255, 255))
        self.lbl_info = wx.StaticText(self, -1, 'info')
        gridSizer = wx.FlexGridSizer(cols=1, vgap=5)
        gridSizer.Add(self.lbl_info, -1, wx.EXPAND)
        self.SetSizer(gridSizer)
        self.bgapp.live_frame = self

    def OnClose(self, event = None):
        self.bgapp.live_frame = None
        self.Destroy()

    def update(self, spew, statistics = None, vod_stats = None):
        if clock() - self.clock > 2:
            self.clock = clock()
            info = ''
            if vod_stats is not None and vod_stats['videostatus'] is not None:
                vs = vod_stats['videostatus']
                info += 'br: ' + str(vs.bitrate / 1024)
                info += ', plen: ' + str(vs.piecelen / 1024)
                info += ', first: ' + str(vs.first_piece)
                info += ', last: ' + str(vs.last_piece)
                info += ', have: ' + str(vs.numhave)
                info += '\nprebuf: ' + str(vs.prebuffering)
                info += ', playing: ' + str(vs.playing)
                info += ', paused: ' + str(vs.paused)
                info += '\nlive_first: ' + str(vs.live_first_piece)
                info += ', live_last: ' + str(vs.live_last_piece)
                info += '\nppos: ' + str(vs.playback_pos)
                if vs.live_first_piece is not None:
                    info += ' -' + str(vs.dist_range(vs.live_first_piece, vs.playback_pos))
                if vs.live_last_piece is not None:
                    info += ', +' + str(vs.dist_range(vs.playback_pos, vs.live_last_piece))
                info += '\nhr: ' + str(vs.get_high_range())
                info += '\nlpos: ' + str(vs.live_startpos)
                info += '\npieces: '
                have = vs.have[:]
                if len(have):
                    p = None
                    f = None
                    t = None
                    for i in sorted(have):
                        if p is None:
                            f = i
                        elif i != p + 1:
                            t = p
                            info += str(f) + '-' + str(t) + ' '
                            f = i
                        p = i

                    info += str(f) + '-' + str(i)
            self.lbl_info.SetLabel(info)


class UserProfileDialog(wx.Dialog):

    def __init__(self, bgapp, icons):
        self.bgapp = bgapp
        self.user_profile = self.bgapp.user_profile
        wx.Dialog.__init__(self, None, -1, self.bgapp.appname + ' ' + self.bgapp.utility.lang.get('user_profile'), size=(400, 200), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.SetIcons(icons)
        grid = wx.GridBagSizer(hgap=5, vgap=8)
        grid.AddGrowableCol(1, 1)
        row = -1
        row += 1
        label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('gender'))
        self.ctrl_gender = wx.ComboBox(self, wx.ID_ANY, choices=[], style=wx.CB_DROPDOWN | wx.CB_READONLY)
        for id, name in self.user_profile.get_genders().iteritems():
            name = self.bgapp.utility.lang.get(name)
            idx = self.ctrl_gender.Append(name, id)
            if id == self.user_profile.get_gender_id():
                self.ctrl_gender.Select(idx)

        grid.Add(label, pos=(row, 0))
        grid.Add(self.ctrl_gender, pos=(row, 1))
        row += 1
        label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('age'))
        self.ctrl_age = wx.ComboBox(self, wx.ID_ANY, choices=[], style=wx.CB_DROPDOWN | wx.CB_READONLY)
        ages = []
        for id, name in self.user_profile.get_ages().iteritems():
            if name.startswith('age_less'):
                priority = ''
            elif name.startswith('age_more'):
                priority = 'z'
            else:
                priority = name
            ages.append((priority, {'id': id,
              'name': name}))

        for priority, age in sorted(ages):
            id = age['id']
            name = age['name']
            name = self.bgapp.utility.lang.get(name)
            idx = self.ctrl_age.Append(name, id)
            if id == self.user_profile.get_age_id():
                self.ctrl_age.Select(idx)

        grid.Add(label, pos=(row, 0))
        grid.Add(self.ctrl_age, pos=(row, 1))
        btn_ok = wx.Button(self, wx.ID_OK, self.bgapp.utility.lang.get('ok'))
        btn_cancel = wx.Button(self, wx.ID_CANCEL, self.bgapp.utility.lang.get('cancel'))
        buttonbox = wx.BoxSizer(wx.HORIZONTAL)
        buttonbox.Add(btn_ok, 0, wx.ALL, 5)
        buttonbox.Add(btn_cancel, 0, wx.ALL, 5)
        mainbox = wx.BoxSizer(wx.VERTICAL)
        mainbox.Add(grid, 1, wx.EXPAND | wx.ALL, border=5)
        mainbox.Add(buttonbox, 0)
        self.SetSizerAndFit(mainbox)
        self.Show()
        self.Bind(wx.EVT_BUTTON, self.OnOK, btn_ok)

    def OnOK(self, event = None):
        if self.save():
            self.EndModal(wx.ID_OK)

    def save(self):
        try:
            gender_id = self.ctrl_gender.GetClientData(self.ctrl_gender.GetSelection())
            age_id = self.ctrl_age.GetClientData(self.ctrl_age.GetSelection())
            self.user_profile.set_gender(gender_id)
            self.user_profile.set_age(age_id)
            self.user_profile.save()
            return True
        except Exception as e:
            print_exc()
            try:
                msg = str(e)
            except:
                msg = 'Cannot save profile'

            dlg = wx.MessageDialog(None, msg, self.bgapp.appname, wx.OK | wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
            return False


class PlayerOptionsDialog(wx.Dialog):

    def __init__(self, bgapp, icons):
        self.bgapp = bgapp
        self.icons = icons
        self.port = None
        self.debug_level = bgapp.debug_level
        self.total_max_connects = self.bgapp.get_playerconfig('total_max_connects', 200)
        self.download_max_connects = self.bgapp.get_playerconfig('download_max_connects', 50)
        auto_down_limit = self.bgapp.get_playerconfig('auto_download_limit', False)
        wait_sufficient_speed = self.bgapp.get_playerconfig('wait_sufficient_speed', False)
        enable_http_support = self.bgapp.get_playerconfig('enable_http_support', True)
        enable_interruptable_ads = self.bgapp.get_playerconfig('enable_interruptable_ads', True)
        downloadrate = self.bgapp.get_playerconfig('total_max_download_rate', 0)
        uploadrate = self.bgapp.get_playerconfig('total_max_upload_rate', 0)
        player_buffer_time = self.bgapp.get_playerconfig('player_buffer_time', 3)
        if DEBUG_LIVE_BUFFER_TIME:
            live_buffer_time = self.bgapp.get_playerconfig('live_buffer_time', 10)
        disk_cache_limit = self.bgapp.get_playerconfig('disk_cache_limit', 0)
        destdir = self.bgapp.get_default_destdir()
        ts_login = self.bgapp.s.get_ts_login()
        ts_password = self.bgapp.s.get_ts_password()
        ts_user_key = self.bgapp.s.get_ts_user_key()
        wx.Dialog.__init__(self, None, -1, self.bgapp.appname + ' Options', size=(400, 200), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.SetIcons(self.icons)
        mainbox = wx.BoxSizer(wx.VERTICAL)
        grid = wx.GridBagSizer(hgap=5, vgap=8)
        grid.AddGrowableCol(1, 1)
        row = -1
        row += 1
        label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('enable_interruptable_ads'))
        self.ctrl_interruptable_ads = wx.CheckBox(self, wx.ID_ANY)
        self.ctrl_interruptable_ads.SetValue(enable_interruptable_ads)
        grid.Add(label, pos=(row, 0))
        grid.Add(self.ctrl_interruptable_ads, pos=(row, 1))
        row += 1
        label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('start_with_sufficient_speed_only'))
        self.ctrl_wait_sufficient_speed = wx.CheckBox(self, wx.ID_ANY)
        self.ctrl_wait_sufficient_speed.SetValue(wait_sufficient_speed)
        grid.Add(label, pos=(row, 0))
        grid.Add(self.ctrl_wait_sufficient_speed, pos=(row, 1))
        row += 1
        label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('auto_determine_download_limit'))
        self.ctrl_auto_down_limit = wx.CheckBox(self, wx.ID_ANY)
        self.ctrl_auto_down_limit.SetValue(auto_down_limit)
        grid.Add(label, pos=(row, 0))
        grid.Add(self.ctrl_auto_down_limit, pos=(row, 1))
        row += 1
        label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('player_buffer_time'))
        self.player_buffer_time_ctrl = wx.TextCtrl(self, wx.ID_ANY, str(player_buffer_time))
        grid.Add(label, pos=(row, 0))
        grid.Add(self.player_buffer_time_ctrl, pos=(row, 1), flag=wx.EXPAND)
        if DEBUG_LIVE_BUFFER_TIME:
            row += 1
            label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('live_buffer_time'))
            self.live_buffer_time_ctrl = wx.TextCtrl(self, wx.ID_ANY, str(live_buffer_time))
            grid.Add(label, pos=(row, 0))
            grid.Add(self.live_buffer_time_ctrl, pos=(row, 1), flag=wx.EXPAND)
        row += 1
        label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('disk_cache_limit'))
        self.disk_cache_limit_ctrl = wx.TextCtrl(self, wx.ID_ANY, str(int(disk_cache_limit / 1073741824)))
        grid.Add(label, pos=(row, 0))
        grid.Add(self.disk_cache_limit_ctrl, pos=(row, 1), flag=wx.EXPAND)
        row += 1
        label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('download_limit'))
        self.downloadratectrl = wx.TextCtrl(self, wx.ID_ANY, str(downloadrate))
        if self.ctrl_auto_down_limit.IsChecked():
            self.downloadratectrl.SetEditable(False)
            self.downloadratectrl.SetBackgroundColour((128, 128, 128))
        grid.Add(label, pos=(row, 0))
        grid.Add(self.downloadratectrl, pos=(row, 1), flag=wx.EXPAND)
        row += 1
        label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('upload_limit'))
        self.uploadratectrl = wx.TextCtrl(self, wx.ID_ANY, str(uploadrate))
        grid.Add(label, pos=(row, 0))
        grid.Add(self.uploadratectrl, pos=(row, 1), flag=wx.EXPAND)
        row += 1
        if self.bgapp.apptype == 'acestream' and sys.platform == 'win32':
            label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('cache_drive'))
            drive_info = []
            drive_list = self.bgapp.get_drive_list()
            curvalue = ''
            for d in drive_list:
                d = self.bgapp.format_drive_name(d)
                total, free, used = self.bgapp.get_disk_info(d + '\\')
                if free is not None:
                    s = str(int(free / 1048576.0)) + ' Mb'
                    info = d + '  (free ' + s + ')'
                    drive_info.append(info)
                    if d == self.bgapp.format_drive_name(destdir):
                        curvalue = info

            self.destdirctrl = wx.ComboBox(self, wx.ID_ANY, choices=drive_info, value=curvalue, style=wx.CB_DROPDOWN | wx.CB_READONLY)
        else:
            label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('downloads_directory'))
            self.destdirctrl = wx.TextCtrl(self, wx.ID_ANY, destdir)
        grid.Add(label, pos=(row, 0))
        grid.Add(self.destdirctrl, pos=(row, 1), flag=wx.EXPAND)
        row += 1
        label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('login'))
        self.ts_login_ctrl = wx.TextCtrl(self, wx.ID_ANY, ts_login)
        grid.Add(label, pos=(row, 0))
        grid.Add(self.ts_login_ctrl, pos=(row, 1), flag=wx.EXPAND)
        row += 1
        label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('password'))
        self.ts_password_ctrl = wx.TextCtrl(self, wx.ID_ANY, ts_password, style=wx.TE_PASSWORD)
        grid.Add(label, pos=(row, 0))
        grid.Add(self.ts_password_ctrl, pos=(row, 1), flag=wx.EXPAND)
        buttonbox2 = wx.BoxSizer(wx.HORIZONTAL)
        advbtn = wx.Button(self, wx.ID_ANY, self.bgapp.utility.lang.get('advanced_etc'))
        buttonbox2.Add(advbtn, 0, wx.ALL, 5)
        buttonbox = wx.BoxSizer(wx.HORIZONTAL)
        okbtn = wx.Button(self, wx.ID_OK, self.bgapp.utility.lang.get('ok'))
        cancelbtn = wx.Button(self, wx.ID_CANCEL, self.bgapp.utility.lang.get('cancel'))
        applybtn = wx.Button(self, wx.ID_ANY, self.bgapp.utility.lang.get('apply'))
        buttonbox.Add(okbtn, 0, wx.ALL, 5)
        buttonbox.Add(cancelbtn, 0, wx.ALL, 5)
        buttonbox.Add(applybtn, 0, wx.ALL, 5)
        mainbox.Add(grid, 1, wx.EXPAND | wx.ALL, border=5)
        mainbox.Add(buttonbox2, 0)
        mainbox.Add(buttonbox, 0)
        self.SetSizerAndFit(mainbox)
        self.Show()
        self.Bind(wx.EVT_BUTTON, self.OnAdvanced, advbtn)
        self.Bind(wx.EVT_BUTTON, self.OnOK, okbtn)
        self.Bind(wx.EVT_BUTTON, self.OnApply, applybtn)
        self.Bind(wx.EVT_CHECKBOX, self.OnCheckboxAutoDownLimit, self.ctrl_auto_down_limit)

    def OnOK(self, event = None):
        if self.OnApply(event):
            self.EndModal(wx.ID_OK)

    def OnCheckboxAutoDownLimit(self, event = None):
        if self.ctrl_auto_down_limit.IsChecked():
            self.downloadratectrl.SetEditable(False)
            self.downloadratectrl.SetBackgroundColour((128, 128, 128))
        else:
            self.downloadratectrl.SetEditable(True)
            self.downloadratectrl.SetBackgroundColour((255, 255, 255))

    def OnApply(self, event = None):
        print >> sys.stderr, 'PlayerOptionsDialog: OnApply: port', self.port
        ts_login = self.ts_login_ctrl.GetValue()
        ts_password = self.ts_password_ctrl.GetValue()
        check_auth = False
        if ts_login != self.bgapp.s.get_ts_login() or ts_password != self.bgapp.s.get_ts_password():
            check_auth = True
        if DEBUG:
            check_auth = True
        self.bgapp.s.set_ts_login(ts_login)
        self.bgapp.s.set_ts_password(ts_password)
        if check_auth:
            self.bgapp.check_auth_level(True)
        session = self.bgapp.s
        state_dir = session.get_state_dir()
        cfgfilename = Session.get_default_config_filename(state_dir)
        scfg = SessionStartupConfig.load(cfgfilename)
        if self.port is not None:
            scfg.set_listen_port(self.port)
        scfg.set_ts_login(ts_login)
        scfg.set_ts_password(ts_password)
        log('systray::options:OnApply: Saving SessionStartupConfig to', cfgfilename)
        scfg.save(cfgfilename)
        try:
            player_buffer_time = int(self.player_buffer_time_ctrl.GetValue())
        except:
            player_buffer_time = 3

        if player_buffer_time < 1:
            player_buffer_time = 1
        if DEBUG_LIVE_BUFFER_TIME:
            try:
                live_buffer_time = int(self.live_buffer_time_ctrl.GetValue())
            except:
                live_buffer_time = 10

            if live_buffer_time < 0:
                live_buffer_time = 0
        try:
            disk_cache_limit = int(self.disk_cache_limit_ctrl.GetValue())
            disk_cache_limit = disk_cache_limit * 1073741824L
        except:
            disk_cache_limit = 0

        destdir = self.destdirctrl.GetValue()
        print >> sys.stderr, 'systray::options:onapply: destdir', destdir, type(destdir)
        if self.bgapp.apptype == 'acestream' and sys.platform == 'win32':
            destdir = self.bgapp.format_drive_name(destdir)
            print >> sys.stderr, 'systray::options:onapply: dest drive', destdir
        elif not self.bgapp.check_dest_dir(destdir, make_hidden=False):
            dlg = wx.MessageDialog(None, self.bgapp.utility.lang.get('options_download_dir_not_writable') % destdir, self.bgapp.appname + self.bgapp.utility.lang.get('options'), wx.OK | wx.ICON_INFORMATION)
            result = dlg.ShowModal()
            dlg.Destroy()
            return False
        changed_config_params = []
        new_config = {'download_dir': destdir,
         'player_buffer_time': player_buffer_time,
         'total_max_upload_rate': int(self.uploadratectrl.GetValue()),
         'total_max_download_rate': int(self.downloadratectrl.GetValue()),
         'auto_download_limit': self.ctrl_auto_down_limit.IsChecked(),
         'wait_sufficient_speed': self.ctrl_wait_sufficient_speed.IsChecked(),
         'enable_interruptable_ads': self.ctrl_interruptable_ads.IsChecked(),
         'disk_cache_limit': disk_cache_limit,
         'total_max_connects': self.total_max_connects,
         'download_max_connects': self.download_max_connects}
        if DEBUG_LIVE_BUFFER_TIME:
            new_config['live_buffer_time'] = live_buffer_time
        for param, new_value in new_config.iteritems():
            old_value = self.bgapp.set_playerconfig(param, new_value)
            if old_value is not None and old_value != new_value:
                changed_config_params.append(param)

        self.bgapp.update_playerconfig(changed_config_params)
        self.bgapp.save_playerconfig()
        self.bgapp.set_debug_level(self.debug_level)
        if self.port is not None and self.port != self.bgapp.s.get_listen_port():
            dlg = wx.MessageDialog(None, self.bgapp.utility.lang.get('options_port_changed'), self.bgapp.appname + self.bgapp.utility.lang.get('restart'), wx.OK | wx.ICON_INFORMATION)
            result = dlg.ShowModal()
            dlg.Destroy()
            self.bgapp.OnExit()
            os._exit(1)
        return True

    def OnAdvanced(self, event = None):
        if self.port is None:
            self.port = self.bgapp.s.get_listen_port()
        dlg = PlayerAdvancedOptionsDialog(self.icons, self.port, self.debug_level, self.total_max_connects, self.download_max_connects, self.bgapp)
        ret = dlg.ShowModal()
        if ret == wx.ID_OK:
            self.port = dlg.get_port()
            if SHOW_DEBUG_LEVEL:
                self.debug_level = dlg.get_debug_level()
            self.total_max_connects = dlg.get_total_max_connects()
            self.download_max_connects = dlg.get_download_max_connects()
        dlg.Destroy()
        if ret == BUTTON_ID_CLEAR_CACHE:
            self.EndModal(wx.ID_CANCEL)


class PlayerAdvancedOptionsDialog(wx.Dialog):

    def __init__(self, icons, port, debug_level, total_max_connects, download_max_connects, bgapp):
        style = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        self.bgapp = bgapp
        wx.Dialog.__init__(self, None, wx.ID_ANY, self.bgapp.appname + ' ' + self.bgapp.utility.lang.get('advanced_options'), size=(400, 200), style=style)
        self.SetIcons(icons)
        mainbox = wx.BoxSizer(wx.VERTICAL)
        aboutbox = wx.BoxSizer(wx.HORIZONTAL)
        aboutbox.Add(wx.StaticText(self, wx.ID_ANY, 'Version'), 1, wx.ALIGN_CENTER_VERTICAL)
        aboutbox.Add(wx.StaticText(self, wx.ID_ANY, VERSION))
        portbox = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('port'))
        self.portctrl = wx.TextCtrl(self, wx.ID_ANY, str(port))
        portbox.Add(label, 1, wx.ALIGN_CENTER_VERTICAL)
        portbox.Add(self.portctrl)
        box1 = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('total_max_connects'))
        self.total_max_connects_ctrl = wx.TextCtrl(self, wx.ID_ANY, str(total_max_connects))
        box1.Add(label, 1, wx.ALIGN_CENTER_VERTICAL)
        box1.Add(self.total_max_connects_ctrl)
        box2 = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('download_max_connects'))
        self.download_max_connects_ctrl = wx.TextCtrl(self, wx.ID_ANY, str(download_max_connects))
        box2.Add(label, 1, wx.ALIGN_CENTER_VERTICAL)
        box2.Add(self.download_max_connects_ctrl)
        if SHOW_DEBUG_LEVEL:
            debugbox = wx.BoxSizer(wx.HORIZONTAL)
            label = wx.StaticText(self, wx.ID_ANY, self.bgapp.utility.lang.get('debug_level'))
            self.debugctrl = wx.TextCtrl(self, wx.ID_ANY, str(debug_level))
            debugbox.Add(label, 1, wx.ALIGN_CENTER_VERTICAL)
            debugbox.Add(self.debugctrl)
        button2box = wx.BoxSizer(wx.HORIZONTAL)
        clearbtn = wx.Button(self, wx.ID_ANY, self.bgapp.utility.lang.get('clear_cache_and_exit'))
        button2box.Add(clearbtn, 0, wx.ALL, 5)
        self.Bind(wx.EVT_BUTTON, self.OnClear, clearbtn)
        buttonbox = wx.BoxSizer(wx.HORIZONTAL)
        okbtn = wx.Button(self, wx.ID_OK, self.bgapp.utility.lang.get('ok'))
        buttonbox.Add(okbtn, 0, wx.ALL, 5)
        cancelbtn = wx.Button(self, wx.ID_CANCEL, self.bgapp.utility.lang.get('cancel'))
        buttonbox.Add(cancelbtn, 0, wx.ALL, 5)
        mainbox.Add(aboutbox, 1, wx.EXPAND | wx.ALL, 5)
        mainbox.Add(portbox, 1, wx.EXPAND | wx.ALL, 5)
        mainbox.Add(box1, 1, wx.EXPAND | wx.ALL, 5)
        mainbox.Add(box2, 1, wx.EXPAND | wx.ALL, 5)
        if SHOW_DEBUG_LEVEL:
            mainbox.Add(debugbox, 1, wx.EXPAND | wx.ALL, 5)
        mainbox.Add(button2box, 1, wx.EXPAND, 1)
        mainbox.Add(buttonbox, 1, wx.EXPAND, 1)
        self.SetSizerAndFit(mainbox)

    def get_port(self):
        return int(self.portctrl.GetValue())

    def get_debug_level(self):
        return int(self.debugctrl.GetValue())

    def get_total_max_connects(self):
        return int(self.total_max_connects_ctrl.GetValue())

    def get_download_max_connects(self):
        return int(self.download_max_connects_ctrl.GetValue())

    def OnClear(self, event = None):
        self.bgapp.clear_session_state()
        self.EndModal(BUTTON_ID_CLEAR_CACHE)
