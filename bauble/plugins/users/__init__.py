
import os
import re

import gtk
from sqlalchemy import *
from sqlalchemy.exc import *
from sqlalchemy.orm.exc import *
from sqlalchemy.ext.declarative import declarative_base, DeclarativeMeta

import bauble
import bauble.editor as editor
from bauble.error import check, CheckConditionError
import bauble.db as db
import bauble.paths as paths
import bauble.pluginmgr as pluginmgr
from bauble.utils.log import debug, warning
import bauble.utils as utils
from bauble.utils.log import debug, warning, error

# WARNING: "roles" are specific to PostgreSQL database from 8.1 and
# greater, therefore this module won't work on earlier PostgreSQL
# databases or other database types

# Read: can select and read data in the database
#
# Write: can add, edit and delete data but can't create new tables,
#        i.e. can't install plugins that create new tables, also
#        shouldn't be able to install a new database over an existing
#        database
#
# Admin: can create other users and grant privileges and create new
#        tables
#


# NOTE: see the following docs for how to get the privileges on a
# specific databas object
# http://www.postgresql.org/docs/8.3/interactive/functions-info.html

# TODO: should allow each of the functions to be called with a
# different connection than db.engine, could probably create a
# descriptor to add the same functionality to all the functions in one
# fell swoop

# TODO: should provide a privilege error that can allow the caller to
# get more information about the error. e.g include the table, the
# permissions, what they were trying to do and the error
# class PrivilegeError(error.BaubleError):
#     """
#     """

#     def __init__(self, ):
#         """
#         """


def connect_as_user(name=None):
    """
    Return a connection where the user is set to name.

    The returned connection should be closed when it is no longer
    needed or deadlocks may occur.
    """
    conn = db.engine.connect()
    # detach connection so when its closed it doesn't go back to the
    # pool where there could be the possibility of it being reused and
    # having future sql commands run as the user afer this connection
    # has been closed
    conn.detach()
    trans = conn.begin()
    try:
        conn.execute('set role %s' % name)
    except Exception, e:
        warning(utils.utf8(e))
        trans.rollback()
        conn.close()
        return None
    else:
        trans.commit()
    return conn


def get_users():
    """Return the list of user names.
    """
    stmt = 'select rolname from pg_roles where rolcanlogin is true;'
    return [r[0] for r in db.engine.execute(stmt)]


def get_groups():
    """Return the list of group names.
    """
    stmt = 'select rolname from pg_roles where rolcanlogin is false;'
    return [r[0] for r in db.engine.execute(stmt)]


def _create_role(name, password=None, login=False, admin=False):
    """
    """
    stmt = 'create role %s INHERIT' % name
    if login:
        stmt += ' LOGIN'
    if admin:
        stmt += ' CREATEROLE'
    if password:
        stmt += ' PASSWORD %s' % password
    #debug(stmt)
    db.engine.execute(stmt)


def create_user(name, password=None, admin=False, groups=[]):
    """
    Create a role that can login.
    """
    _create_role(name, password, login=True, admin=False)
    for group in groups:
        stmt = 'grant %s to %s;' % (group, name)
        db.engine.execute(stmt)
    # allow the new role to connect to the database
    stmt = 'grant connect on database %s to %s' % \
        (bauble.db.engine.url.database, name)
    #debug(stmt)
    db.engine.execute(stmt)


def create_group(name, admin=False):
    """
    Create a role that can't login.
    """
    _create_role(name, login=False, password=None, admin=admin)


def add_member(name, groups=[]):
    """
    Add name to groups.
    """
    conn = db.engine.connect()
    trans = conn.begin()
    try:
        for group in groups:
            stmt = 'grant "%s" to %s;' % (group, name)
            conn.execute(stmt)
    except:
        trans.rollback()
    else:
        trans.commit()
    finally:
        conn.close()


def remove_member(name, groups=[]):
    """
    Remove name from groups.
    """
    conn = db.engine.connect()
    trans = conn.begin()
    try:
        for group in groups:
            stmt = 'revoke %s from %s;' % (group, name)
            conn.execute(stmt)
    except:
        trans.rollback()
    else:
        trans.commit()
    finally:
        conn.close()


def get_members(group):
    """Return members of group

    Arguments:
    - `group`:
    """
    # get group id
    stmt = "select oid from pg_roles where rolname = '%s'" % group
    gid = db.engine.execute(stmt).fetchone()[0]
    # get members with the gid
    stmt = "select member from pg_auth_members where roleid = '%s'" % gid
    roleids = [r[0] for r in db.engine.execute(stmt).fetchall()]
    stmt = 'select rolname from pg_roles where oid in (select member ' \
        'from pg_auth_members where roleid = %s)' % gid
    return [r[0] for r in db.engine.execute(stmt).fetchall()]


def delete(role, revoke=False):
    """See drop()
    """
    drop(role, revoke)


def drop(role, revoke=False):
    """
    Drop a user from the database

    Arguments:
    - `role`:
    - `revoke`: If revoke is True then revoke the users permissions
      before dropping them
    """
    # TODO: need to revoke all privileges first
    conn = db.engine.connect()
    trans = conn.begin()
    try:
        if revoke:
            for table in db.metadata.sorted_tables:
                stmt = 'revoke all on table %s from %s;' % (table.name, role)
                conn.execute(stmt)
                stmt = 'revoke all on database %s from %s' \
                    % (bauble.db.engine.url.database, role)
            conn.execute(stmt)
        stmt = 'drop role %s;' % (role)
        conn.execute(stmt)
    except Exception, e:
        error(e)
        trans.rollback()
    else:
        trans.commit()
    finally:
        conn.close()


def get_privileges(role):
    """Return the privileges the user has on the current database.

    Arguments:
    - `role`:
    """
    # TODO: should we return read, write, admin or the specific
    # privileges...this can basically just be a wrapped call to
    # has_privileges()
    raise NotImplementedError


_privileges = {'read': ['connect', 'select'],
              'write': ['connect', 'usage', 'select', 'update', 'insert',
                        'delete', 'execute', 'trigger', 'references'],
              'admin': ['all']}

_database_privs = ['create', 'temporary', 'temp']

_table_privs = ['select', 'insert', 'update', 'delete', 'references',
                 'trigger', 'all']

__sequence_privs = ['usage', 'select', 'update', 'all']


def _parse_acl(acl):
    """
    returns a list of acls of (role, privs, granter)
    """
    rx = re.compile('[{]?(.*?)=(.*?)\/(.*?)[,}]')
    return rx.findall(acl)


def has_privileges(role, privilege):
    """Return True/False if role has privileges.

    Arguments:
    - `role`:
    - `privileges`:
    """
    # if the user has all on database with grant privileges he has
    # the grant privilege on the database then he has admin

    if privilege == 'admin':
        # test admin privileges on the database
        for priv in _database_privs:
            stmt = "select has_database_privilege('%s', '%s', '%s')" \
                % (role, bauble.db.engine.url.database, priv)
            r = db.engine.execute(stmt).fetchone()[0]
            if not r:
                # debug('%s does not have %s on database %s' % \
                #           (role, priv, bauble.db.engine.url.database))
                return False
        privs = set(_table_privs).intersection(_privileges['write'])
    else:
        privs = set(_table_privs).intersection(_privileges[privilege])


    # TODO: can we call had_table_privileges on a sequence

    # test the privileges on the tables and sequences
    for table in db.metadata.sorted_tables:
        for priv in privs:
            stmt = "select has_table_privilege('%s', '%s', '%s')" \
                % (role, table.name, priv)
            r = db.engine.execute(stmt).fetchone()[0]
            if not r:
                # debug('%s does not have %s on %s table' % \
                #           (role,priv,table.name))
                return False
    return True



def set_privilege(role, privilege):
    """Set the role's privileges.

    Arguments:
    - `role`:
    - `privilege`:
    """
    check(privilege in ('read', 'write', 'admin', None),
          'invalid privilege: %s' % privilege)
    conn = db.engine.connect()
    trans = conn.begin()

    if privilege:
        privs = _privileges[privilege]

    try:
        # revoke everything first
        for table in db.metadata.sorted_tables:
            stmt = 'revoke all on table %s from %s;' % (table.name, role)
            conn.execute(stmt)
            stmt = 'revoke all on database %s from %s' \
                % (bauble.db.engine.url.database, role)
            conn.execute(stmt)

        # privilege is None so all permissions are revoked
        if not privilege:
            trans.commit()
            conn.close()
            return

        # change privileges on the database
        if privilege == 'admin':
            stmt = 'grant all on database %s to %s' % \
                (bauble.db.engine.url.database, role)
            if privilege == 'admin':
                    stmt += ' with grant option'
            conn.execute(stmt)

        # grant privileges on the tables and sequences
        for table in bauble.db.metadata.sorted_tables:
            tbl_privs = filter(lambda x: x.lower() in _table_privs, privs)
            for priv in tbl_privs:
                stmt = 'grant %s on %s to %s' % (priv, table.name, role)
                if privilege == 'admin':
                    stmt += ' with grant option'
                #debug(stmt)
                conn.execute(stmt)
            for col in table.c:
                seq_privs = filter(lambda x: x.lower() in __sequence_privs,
                                   privs)
                for priv in seq_privs:
                    if hasattr(col, 'sequence'):
                        stmt = 'grant %s on sequence %s to %s' % \
                            (priv, col.sequence.name, role)
                        #debug(stmt)
                        if privilege == 'admin':
                            stmt += ' with grant option'
                        conn.execute(stmt)
    except Exception, e:
        error(e)
        trans.rollback()
    else:
        trans.commit()
    finally:
        conn.close()


def current_user():
    """Return the name of the current user.
    """
    return db.engine.execute('select current_user;').fetchone()[0]


class UsersEditor(editor.GenericEditorView):
    """
    """

    def __init__(self, ):
        """
        """
        filename = os.path.join(paths.lib_dir(), 'plugins', 'users','ui.glade')
        super(UsersEditor, self).__init__ (filename)

        if not db.engine.name == 'postgres':
            msg = _('The Users editor is only valid on a PostgreSQL database')
            utils.message_dialog(utils.utf8(msg))
            return

        # TODO: should allow anyone to view the priveleges but only
        # admins to change them
        debug(current_user())
        if not has_privileges(current_user(), 'admin'):
            msg = _('You do not have privileges to change other '\
                        'user privileges')
            utils.message_dialog(utils.utf8(msg))
            return
        # setup the users tree
        tree = self.widgets.users_tree

        # remove any old columns
        for column in tree.get_columns():
            tree.remove_column(column)

        renderer = gtk.CellRendererText()
        def cell_data_func(col, cell, model, it):
            value = model[it][0]
            cell.set_property('text', value)
        tree.insert_column_with_data_func(0, _('Users'), renderer,
                                          cell_data_func)
        model = gtk.ListStore(str)
        for user in get_users():
            model.append([user])
        self.widgets.users_tree.set_model(model)

        self.connect(tree, 'cursor-changed', self.on_cursor_changed)
        tree.set_cursor("0")

        def on_toggled(button, priv=None):
            buttons = (self.widgets.read_button, self.widgets.write_button,
                       self.widgets.admin_button)
            path, column = tree.get_cursor()
            role = tree.get_model()[path][0]
            active = button.get_active()
            if active and not has_privileges(role, priv):
                #debug('grant %s to %s' % (priv, role))
                set_privilege(role, priv)
            return True

        self.connect('read_button', 'toggled', on_toggled, 'read')
        self.connect('write_button', 'toggled', on_toggled, 'write')
        self.connect('admin_button', 'toggled', on_toggled, 'admin')

        # connect password button
        self.connect('pwd_button', 'clicked', self.on_pwd_button_clicked)


    def on_pwd_button_clicked(self, button, *args):
        dialog = self.widgets.pwd_dialog
        dialog.set_transient_for(self.get_window())
        def _on_something(d, *args):
            d.hide()
            return True
        self.connect(dialog,  'delete-event', _on_something)
        self.connect(dialog, 'close', _on_something)
        self.connect(dialog, 'response', _on_something)
        self.widgets.pwd_entry1.set_text('')
        self.widgets.pwd_entry2.set_text('')
        response = dialog.run()
        debug(response)
        if response == gtk.RESPONSE_OK:
            pwd1 = self.widgets.pwd_entry1.get_text()
            pwd2 = self.widgets.pwd_entry2.get_text()
            debug('%s -- %s' % (pwd1, pwd2))
            tree = self.widgets.users_tree
            path, col = tree.get_cursor()
            user = tree.get_model()[path][0]
            debug(user)
            if pwd1 == '' or pwd2 == '':
                msg = _('The password for user <b>%s</b> has not been ' \
                        'changed.' % user)
                utils.message_dialog(msg, gtk.MESSAGE_WARNING,
                                     parent=self.get_window())
                return
            elif pwd1 != pwd2:
                msg = _('The passwords do not match.  The password for '\
                            'user <b>%s</b> has not been changed.' % user)
                utils.message_dialog(msg, gtk.MESSAGE_WARNING,
                                     parent=self.get_window())
                return
        # TODO: show a dialog that says the pwd has been changed or
        # just put a message in the status bar




    def get_window(self):
        return self.widgets.main_dialog


    def start(self):
        self.get_window().run()
        self.cleanup()


    buttons = {'admin': 'admin_button',
               'write': 'write_button',
               'read': 'read_button'}
    def on_cursor_changed(self, tree):
        path, column = tree.get_cursor()
        #debug(tree.get_model()[path][column])
        role = tree.get_model()[path][0]
        def _set_buttons(mode):
            #debug('%s: %s' % (role, mode))
            if mode:
                self.widgets[self.buttons[mode]].set_active(True)
            not_modes = filter(lambda p: p != mode, self.buttons.keys())
            for m in not_modes:
                self.widgets[self.buttons[m]].props.active = False
        if has_privileges(role, 'admin'):
            _set_buttons('admin')
        elif has_privileges(role, 'write'):
            _set_buttons('write')
        elif has_privileges(role, 'read'):
            _set_buttons('read')
        else:
            _set_buttons(None)




class UsersTool(pluginmgr.Tool):

    label = _("Users")

    @classmethod
    def start(self):
        UsersEditor().start()

# TODO: need some way to disable the plugin/tool if not a postgres database

class UsersPlugin(pluginmgr.Plugin):

    tools = []

    @classmethod
    def init(cls):
        if bauble.db.engine.name != 'postgres':
            del cls.tools[:]
        elif bauble.db.engine.name == 'postgres' and not cls.tools:
            cls.tools.append(UsersTool)

plugin = UsersPlugin
