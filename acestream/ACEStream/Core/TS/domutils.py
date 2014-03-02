#Embedded file name: ACEStream\Core\TS\domutils.pyo
from traceback import print_exc
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False

class domutils:

    @staticmethod
    def get_tag_value(xmldoc, tagname):
        a = xmldoc.getElementsByTagName(tagname)
        if len(a) == 0:
            if DEBUG:
                log('domutils::get_tag_value: tag not found: tagname', tagname)
            return None
        if len(a) > 1:
            raise ValueError, 'Tag not unique: ' + tagname
        return domutils.get_node_text(a[0])

    @staticmethod
    def get_node_text(node, trim = True):
        try:
            value = ''
            for n in node.childNodes:
                if n.nodeType == node.TEXT_NODE or n.nodeType == node.CDATA_SECTION_NODE:
                    value += n.data

            if trim:
                value = value.strip()
            return value
        except:
            if DEBUG:
                print_exc()
            return ''

    @staticmethod
    def get_children_by_tag_name(node, tagname):
        nodes = []
        for child in node.childNodes:
            if child.nodeType == child.ELEMENT_NODE:
                if child.tagName == tagname:
                    nodes.append(child)

        return nodes

    @staticmethod
    def get_single_element(parent, tagname, required = True):
        children = domutils.get_children_by_tag_name(parent, tagname)
        if len(children) == 0:
            if required:
                raise ValueError, 'Missing element ' + tagname
            else:
                return None
        if len(children) > 1:
            raise ValueError, 'Single child expected: tagname ' + tagname
        return children[0]
