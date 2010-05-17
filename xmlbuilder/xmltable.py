from PyQt4.QtGui import QUndoStack, QUndoCommand, QColor
from PyQt4.QtCore import QStringList, Qt, QAbstractTableModel, QMimeData, \
    QVariant, SIGNAL, QString, QModelIndex
import re, time
from commands import ChangeValueCommand, RowCommand

class Table(QAbstractTableModel):

    def __init__(self, ob, parent):
        QAbstractTableModel.__init__(self)
        # store things
        self.ob = ob
        self.stack = QUndoStack()
        self._parent = parent
        # Make sure we have Name information first
        # _header contains the row headers
        self._header = [
            QVariant('#'), QVariant(getattr(self.ob, 'UniqueName', 'name'))]
        # _tooltips contains the tooltips
        self._tooltips = [
            QVariant('Row is commented out %s'%bool),
            QVariant('Object name %s'%str)]
        # _required is a list of required columns
        self._required = []
        # _defaults is a dict of column -> default values
        self._defaults = {0: QVariant(False)}
        # _optional is a list of optional columns
        self._optional = [1]
        # _cItems is a dict of column -> QVariant QStringList items, returned
        # to combo box
        self._cItems = {}
        # _cValues is a dict of column -> list of QVariant values, stored when
        # corresponding label stored by combobox
        self._cValues = {}
        # _idents is a list of identifier lookup fields
        self._idents = []
        # _types is a list of types for validation
        self._types = [bool, str]
        # rows is a list of rows. each row is a list of QVariants
        self.rows = []
        # _needsname tells use whether to pass the name to the object, or just
        # use it as the objects identifier
        self._needsname = False
        # work out the header and descriptions from the ArgInfo object
        a = ob.ArgInfo
        # for required names just process the ArgType object
        for name in a.required_names:
            self.__processArgType(name, a.descriptions[name])
        # for defaulted names give it a default too
        for name, default in zip(a.default_names, a.default_values):
            self.__processArgType(name, a.descriptions[name], default = default)
        # for optional names flag it as optional
        for name in a.optional_names:
            self.__processArgType(name, a.descriptions[name], optional = True)
        # maps (filt, without, upto) -> (timestamp, stringList)
        self._cachedNameList = {}

    def __processArgType(self, name, ob, **args):
        # this is the column index
        col = len(self._header)
        # If it's a name then be careful not to add it twice
        if name == getattr(self.ob, 'UniqueName', 'name'):
            self._needsname = True
            assert ob.typ == str, 'Object name must be a string'
            self._tooltips[1] = QVariant(ob.desc)
        else:
            # add the header, type and tooltip
            self._header.append(QVariant(name))
            self._types.append(ob.typ)
            self._tooltips.append(QVariant(ob.desc))
        # if we have a default value, set it
        if 'default' in args:
            if args['default'] is None:
                self._defaults[col] = QVariant('None')
            else:
                self._defaults[col] = QVariant(args['default'])
        # if this is optional
        elif 'optional' in args:
            self._optional.append(col)
        # it must be required
        else:
            self._required.append(col)
        # if we have combo box items
        if hasattr(ob, 'labels'):
            self._cItems[col] = QVariant(
                QStringList([QString(str(x)) for x in ob.labels]))
        # if we have combo box values
        if hasattr(ob, 'values'):
            self._cValues[col] = [QVariant(x) for x in ob.values]
        # if it's an ident
        if hasattr(ob, 'ident'):
            self._idents.append(col)

    def __convert(self, variant, typ, py=False):
        # convert to the requested type
        if typ == bool:
            return (variant.toBool(), True)
        elif typ == int:
            return variant.toInt()
        elif typ == float:
            val, ret = variant.toDouble()
            if py:
                return (str(variant.toString()), ret)
            else:
                return (variant.toString(), ret)
        elif typ == str:
            if py:
                return (str(variant.toString()), True)
            else:
                return (variant.toString(), True)
        else:
            return (variant, False)

    def __lookup(self, i, val, obs):
        if val.isNull():
            val = self._defaults[i]
        if i in self._idents:
            val = str(val.toString())
            if obs is not None:
                if val == 'None':
                    val = None
                else:
                    assert val in obs, \
                        'Ident lookup failed on %s in obs %s' % (val, obs)
                    val = obs[val]
        else:
            val = self.__convert(val, self._types[i], py=True)[0]
        return val

    def __createArgDict(self, row, obs = None):
        # create an arg dictionary
        args = {}
        # lookup and add attributes
        header = [ str(x.toString()) for x in self._header ]
        debug = self._parent._objectName(self.ob) + '('
        if self._needsname or (obs is None):
            i = 1
        else:
            i = 2
        while i < len(row):
            if row[i].isNull():
                i += 1
                continue
            attr = header[i]
            val =  self.__lookup(i, row[i], obs)
            if obs is not None and self._parent.debug:
                if i in self._idents:
                    debugval = self.__lookup(i, row[i], None)
                else:
                    debugval = val.__repr__()
                debug += attr + '=' + debugval  + ', '
            i += 1
            args[attr] = val
        if obs is not None and self._parent.debug:
            print debug[:-2] + ')'
        return args

    def createElements(self, doc, name):
        # create xml elements from this table
        for row in self.rows:
            args = self.__createArgDict(row)
            el = doc.createElement(name)
            # lookup and add attributes
            for k, v in args.items():
                el.setAttribute(k, str(v))
            if row[0].toBool() == True:
                el = doc.createComment(el.toxml())
            doc.documentElement.appendChild(el)

    def createObjects(self, obs):
        for row in self.rows:
            # ignore commented rows
            if row[0].toBool() == True:
                continue
            if self._parent.debug:
                if not row[1].isNull():
                    print str(row[1].toString()), '=',
            args = self.__createArgDict(row, obs)
            ob = self.ob(**args)
            # if we have a name, store it in ret
            if not row[1].isNull():
                obs[str(row[1].toString())] = ob

    def addNode(self, node, commented = False):
        # add xml nodes as rows in the table
        w = []
        row = [ QVariant() ] * len(self._header)
        if commented:
            row[0] = QVariant(True)
        else:
            row[0] = QVariant(False)
        for attr, value in node.attributes.items():
            attr = str(attr)
            value = str(value)
            index = -1
            for i, item in enumerate(self._header):
                if str(item.toString()) == attr:
                    index = i
                    break
            if index == -1:
                w.append('%s doesn\'t have attr %s' % (node.nodeName, attr))
                continue
            typ = self._types[index]
            try:
                if typ == int:
                    value = int(value)
                elif typ == bool:
                    value = (value == 'True')
            except:
                w.append(
                    '%s.%s = %s, can\'t convert to %s' %
                    (node.nodeName, attr, value.__repr__(), typ))
            row[index] = QVariant(value)
        # add the row to the table
        self.rows.append(row)
        return w

    def flags(self, index):
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable

    def rowCount(self, parent = None):
        return len(self.rows)

    def columnCount(self, parent = None):
        return len(self._header)

    def headerData(self, section, orientation, role = Qt.DisplayRole ):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self._header[section]
            elif self.rows and self.rows[section] and \
                    not self.rows[section][1].isNull():
                return self.rows[section][1]
            else:
                return QVariant('[row %s]' % (section+1))
        elif role == Qt.ToolTipRole and orientation == Qt.Horizontal:
            return self._tooltips[section]
        else:
            return QVariant()


    # put the change request on the undo stack
    def setData(self, index, val, role=Qt.EditRole):
        if role == Qt.EditRole and \
                val != self.rows[index.row()][index.column()]:
            col = index.column()
            if col in self._cValues:
                # lookup the display in the list of _cItems
                for i, v in enumerate(self._cItems[col].toStringList()):
                    if v.toLower() == val.toString().toLower():
                        val = QVariant(i)
            self.stack.push(
                ChangeValueCommand(index.row(), index.column(), val, self))
            return True
        else:
            return False

    def insertRows(self, row, count, parent = QModelIndex()):
        if count > 1:
            self.stack.beginMacro('Insert rows %d..%d'%(row+1, row+count))
        for row in range(row, row+count):
            self.stack.push(RowCommand(row, self, parent))
        if count > 1:
            self.stack.endMacro()

    def removeRows(self, row, count, parent = QModelIndex()):
        if count > 1:
            self.stack.beginMacro('Remove rows %d..%d'%(row+1, row+count))
        for row in reversed(range(row, row+count)):
            self.stack.push(RowCommand(row, self, parent, False))
        if count > 1:
            self.stack.endMacro()


    def _isCommented(self, row):
        return self.rows[row][0].toBool()

    def _nameList(self, filt = None, without = None, upto = None):
        # need to search all tables for a string list of object names
        # filt is a ModuleBase subclass to filter by
        # without is a row number to exclude from the current table
        # upto means only look at objects up to "upto" row in the current table
        if (filt, without, upto) in self._cachedNameList:
            timestamp, sl = self._cachedNameList[(filt, without, upto)]
            if self._parent.lastModified() <= timestamp:
                return sl
        sl = QStringList()
        for name in self._parent.getTableNames():
            table = self._parent._tables[name]
            # if we have a filter, then make sure this table is a subclass of it
            if filt is not None and not issubclass(table.ob, filt):
                # if we are only going up to a certain table and this is it
                if table == self and upto is not None:
                    return sl
                continue
            for i,trow in enumerate(table.rows):
                if table == self:
                    # if the current table is self, make sure we are excluding
                    # the without row
                    if without is not None and without == i:
                        continue
                    # make sure we only go up to upto
                    if upto is not None and upto == i:
                        return sl
                # add a non-null name, which is not commented out to the list
                if not trow[1].isNull() and not \
                        (not trow[0].isNull() and trow[0].toBool() == True):
                    sl.append(trow[1].toString())
        # store the cached value
        self._cachedNameList[(filt, without, upto)] = (time.time(), sl)
        return sl

    def _isInvalid(self, value, row, col):
        # check that required rows are filled in
        if value.isNull():
            if col in self._required:
                return 'Required argument not filled in'
            else:
                return False
        # check that names are unique
        elif col == 1:
            name = value.toString()
            index = self._nameList(without = row).indexOf(name)
            if index != -1:
                return 'Object with name "%s" already exists' % name
        # check that idents are valid
        elif col in self._idents:
            name = value.toString()
            ob = self._types[col]
            index = self._nameList(filt = ob, upto = row).indexOf(name)
            if index == -1:
                return 'Can\'t perform identifier lookup on "%s"' % name
        # check that enums are valid
        elif col in self._cValues:
            if not max([value == x for x in self._cValues[col]]):
                return '"%s" is not a supported enum' % value.toString()
        # check that choices are valid
        elif col in self._cItems:
            if not max(
                [value == QVariant(x)
                 for x in self._cItems[col].toStringList()]):
                return '"%s" is not a supported choice' % value.toString()
        # check the type of basetypes
        else:
            typ = self._types[col]
            v, ret = self.__convert(value, typ)
            if ret != True:
                return 'Cannot convert "%s" to %s' % (value.toString(), typ)
        return False

    def _isDefault(self, value, col):
        return value.isNull() and col in self._defaults

    def data(self, index, role):
        col = index.column()
        row = index.row()
        value = self.rows[row][col]
        if role == Qt.DisplayRole:
            # default view
            if self._isDefault(value, col):
                value = self._defaults[col]
            if col in self._cValues:
                # lookup the display in the list of _cItems
                for i, v in enumerate(self._cValues[col]):
                    if v == value:
                        return QVariant(self._cItems[col].toStringList()[i])
            elif col == 0:
                if value.toBool():
                    return QVariant(QString('#'))
                else:
                    return QVariant(QString(''))
            elif not value.isNull() and self._types[col] == str and \
                    str(value.toString()) == '':
                value = QVariant(QString('""'))
            return value
        elif role == Qt.EditRole:
            # text editor
            if self._isDefault(value, col):
                value = self._defaults[col]
            if col in self._cValues:
                # lookup the display in the list of _cItems
                for i, v in enumerate(self._cValues[col]):
                    if v == value:
                        return QVariant(self._cItems[col].toStringList()[i])
            v, ret = self.__convert(value, self._types[col])
            if not value.isNull() and str(v) == '':
                v = '""'
            return QVariant(v)
        elif role == Qt.ToolTipRole:
            # tooltip
            error = self._isInvalid(value, row, col)
            text = str(self._tooltips[col].toString())
            if error:
                text = '***Error: %s\n%s'%(error, text)
            if col in self._idents:
                lines = ['\nPossible Values: ']
                for name in self._nameList(filt = self._types[col], upto = row):
                    if len(lines[-1]) > 80:
                        lines.append('')
                    lines[-1] += str(name) + ', '
                text += '\n'.join(lines).rstrip(' ,')
            return QVariant(text)
        elif role == Qt.ForegroundRole:
            # cell foreground
            if self._isCommented(row):
                # comment
                return QVariant(QColor(120,140,180))
            if self._isDefault(value, col):
                # is default arg (always valid)
                return QVariant(QColor(160,160,160))
            elif self._isInvalid(value, row, col):
                # invalid
                return QVariant(QColor(255,0,0))
            else:
                # valid
                return QVariant(QColor(0,0,0))
        elif role == Qt.BackgroundRole:
            # cell background
            if self._isCommented(row):
                # commented
                return QVariant(QColor(160,180,220))
            elif self._isInvalid(value, row, col):
                # invalid
                return QVariant(QColor(255,200,200))
            elif col in self._defaults:
                # has default
                return QVariant(QColor(255,255,240))
            elif col in self._optional:
                #is optional
                return QVariant(QColor(180,180,180))
            else:
                # valid
                return QVariant(QColor(250,250,250))
        elif role == Qt.UserRole:
            # combo box asking for list of items
            if col in self._idents:
                return QVariant(
                    self._nameList(filt = self._types[col], upto = row))
            elif col in self._cItems:
                return self._cItems[col]
            elif self._types[col] == bool:
                return QVariant(True)
            else:
                return QVariant()
        else:
            return QVariant()

    def clearIndexes(self, indexes):
        # clear cells from a list of QModelIndex's
        begun = False
        for item in indexes:
            if not self.rows[item.row()][item.column()].isNull():
                if not begun:
                    begun = True
                    celltexts = [ '(%s, %d)' %
                        (self._header[c.column()].toString(), c.row() + 1) \
                        for c in indexes ]
                    self.stack.beginMacro('Cleared Cells: '+' '.join(celltexts))
                self.setData(item, QVariant(), Qt.EditRole)
        if begun:
            self.stack.endMacro()