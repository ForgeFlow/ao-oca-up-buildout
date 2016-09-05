#!/usr/bin/python
import psycopg2
import sys, getopt


def help_message():
    print '''post-migration.py -- uses getopt to recognize options
Options: -h      -- displays this help message
       --db_name= -- the name of the database
       --db_user=  -- user to execute the sql sentences
       --db_password= --password to execute the sql sentences'''
    sys.exit(0)
try:
    options, xarguments = getopt.getopt(sys.argv[1:], 'h',
                                        ['db_name=',
                                         'db_user=', 'db_password='])
except getopt.error:
    print 'Error: You tried to use an unknown option or the argument for an ' \
          'option that requires it was missing. Try pre-migration.py -h\' ' \
          'for more information.'
    sys.exit(0)

for a in options[:]:
    if a[0] == '--db_name' and a[1] != '':
        db_name = a[1]
        options.remove(a)
        break
    elif a[0] == '--db_name' and a[1] == '':
        print '--db_name expects an argument'
        sys.exit(0)

for a in options[:]:
    if a[0] == '--db_user' and a[1] != '':
        db_user = a[1]
        options.remove(a)
        break
    elif a[0] == '--db_user' and a[1] == '':
        print '--db_user expects an argument'
        sys.exit(0)

db_password = False
for a in options[:]:
    if a[0] == '--db_password' and a[1] != '':
        db_password = a[1]
        options.remove(a)
        break


def disable_inherit_unported_modules(conn, cr):
    print("""defuse inheriting views originating from
    not yet ported modules""")
    cr.execute("""
        UPDATE ir_ui_view
        SET arch='<data/>'
        FROM ir_model_data
        JOIN ir_module_module
        ON ir_model_data.module=ir_module_module.name
        WHERE ir_model_data.model='ir.ui.view'
        AND res_id=ir_ui_view.id
        AND inherit_id IS NOT null
        AND ir_module_module.state <> 'installed'
    """)
    conn.commit()


def set_not_ported_modules_to_installed(conn, cr):
    print("""set not yet ported modules to installed
    (otherwise, updating a module to work on becomes tricky)""")

    cr.execute("""
        UPDATE ir_module_module
        SET state='installed'
        WHERE state IN ('to install', 'to upgrade')
    """)
    conn.commit()


def deactivate_features(conn, cr):
    print("""deactivate cronjobx, mailservers, fetchmail""")

    cr.execute("""DELTE FROM ir_mail_server""")
    cr.execute("""UPDATE fetchmail_server SET active=False""")
    cr.execute("""UPDATE ir_cron SET active=False""")
    conn.commit()


def reset_all_users_passwords(conn, cr):
    print("""reset all user passwords""")
    cr.execute("""
        UPDATE res_users
        SET password_crypt=(
            SELECT password_crypt
            FROM res_users
            WHERE login='admin')
        """)
    conn.commit()


def main():
    # Define our connection string
    conn_string = """dbname=%s user=%s
    password=%s""" % (db_name, db_user, db_password)

    # print the connection string we will use to connect
    print "Connecting to database\n	->%s", conn_string

    # get a connection, if a connect cannot be made an exception
    # will be raised here
    conn = psycopg2.connect(conn_string)

    # conn.cursor will return a cursor object, you can use this cursor
    # to perform queries
    cr = conn.cursor()
    print "Connected!\n"

    disable_inherit_unported_modules(conn, cr)
    set_not_ported_modules_to_installed(conn, cr)
    deactivate_features(conn, cr)
    reset_all_users_passwords(conn, cr)


if __name__ == "__main__":
    main()
