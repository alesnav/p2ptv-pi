#Embedded file name: ACEStream\Core\BuddyCast\similarity.pyo
__fool_epydoc = 481
from sets import Set

def P2PSim(pref1, pref2):
    cooccurrence = len(Set(pref1) & Set(pref2))
    if cooccurrence == 0:
        return 0
    normValue = (len(pref1) * len(pref2)) ** 0.5
    _sim = cooccurrence / normValue
    sim = int(_sim * 1000)
    return sim


def getCooccurrence(pref1, pref2):
    i = 0
    j = 0
    co = 0
    size1 = len(pref1)
    size2 = len(pref2)
    if size1 == 0 or size2 == 0:
        return 0
    while 1:
        if i >= size1 or j >= size2:
            break
        Curr_ID1 = pref1[i]
        Curr_ID2 = pref2[j]
        if Curr_ID1 < Curr_ID2:
            i = i + 1
        elif Curr_ID1 > Curr_ID2:
            j = j + 1
        else:
            co += 1
            i += 1
            j += 1

    return co


def P2PSimSorted(pref1, pref2):
    cooccurrence = getCooccurrence(pref1, pref2)
    if cooccurrence == 0:
        return 0
    normValue = (len(pref1) * len(pref2)) ** 0.5
    _sim = cooccurrence / normValue
    sim = int(_sim * 1000)
    return sim


def P2PSimLM(peer_permid, my_pref, peer_pref, owners, total_prefs, mu = 1.0):
    npeerprefs = len(peer_pref)
    if npeerprefs == 0 or total_prefs == 0:
        return 0
    nmyprefs = len(my_pref)
    if nmyprefs == 0:
        return 0
    PmlU = float(npeerprefs) / total_prefs
    PmlIU = 1.0 / nmyprefs
    peer_sim = 0.0
    for item in owners:
        nowners = len(owners[item]) + 1
        cUI = item in peer_pref
        PbsUI = float(cUI + mu * PmlU) / (nowners + mu)
        peer_sim += PbsUI * PmlIU

    return peer_sim * 100000


def P2PSim_Single(db_row, nmyprefs):
    sim = 0
    if db_row:
        peer_id, nr_items, overlap = db_row
        if nr_items is None or nmyprefs is None:
            return sim
        if nr_items == 0 or nmyprefs == 0:
            return sim
        sim = overlap * (1.0 / nmyprefs ** 0.5 * (1.0 / nr_items ** 0.5))
        if nr_items < 40:
            sim = nr_items / 40.0 * sim
    return sim


def P2PSim_Full(db_rows, nmyprefs):
    similarity = {}
    for db_row in db_rows:
        similarity[db_row[0]] = P2PSim_Single(db_row, nmyprefs)

    return similarity


def P2PSimColdStart(choose_from, not_in, nr):
    allready_choosen = [ permid for version, sim, permid in not_in ]
    options = []
    for permid in choose_from:
        if permid not in allready_choosen:
            options.append([choose_from[permid]['num_torrents'], [choose_from[permid]['oversion'], 0.0, permid]])

    options.sort()
    options.reverse()
    options = [ row[1] for row in options[:nr] ]
    return options
