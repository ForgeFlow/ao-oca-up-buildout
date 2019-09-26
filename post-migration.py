#!/usr/bin/python
import psycopg2
import sys
import getopt
import json


def help_message():
    print('''post-migration.py -- uses getopt to recognize options
Options: -h      -- displays this help message
       --db_name= -- the name of the database
       --db_user=  -- user to execute the sql sentences
       --db_password= --password to execute the sql sentences
       --db_host= --host for connection (optional)
       --db_port= --port for connection (optional)''')
    sys.exit(0)


try:
    options, xarguments = getopt.getopt(
        sys.argv[1:], 'h',
        ['db_name=', 'db_user=', 'db_password=', 'db_host=', 'db_port='])
except getopt.error:
    print('Error: You tried to use an unknown option or the argument for an '
          'option that requires it was missing. Try pre-migration.py -h\' '
          'for more information.')
    sys.exit(0)

for a in options[:]:
    if a[0] == '--db_name' and a[1] != '':
        db_name = a[1]
        options.remove(a)
        break
    elif a[0] == '--db_name' and a[1] == '':
        print('--db_name expects an argument')
        sys.exit(0)

for a in options[:]:
    if a[0] == '--db_user' and a[1] != '':
        db_user = a[1]
        options.remove(a)
        break
    elif a[0] == '--db_user' and a[1] == '':
        print('--db_user expects an argument')
        sys.exit(0)

db_password = False
for a in options[:]:
    if a[0] == '--db_password' and a[1] != '':
        db_password = a[1]
        options.remove(a)
        break

db_host = False
for a in options[:]:
    if a[0] == '--db_host' and a[1] != '':
        db_host = a[1]
        options.remove(a)
        break

db_port = False
for a in options[:]:
    if a[0] == '--db_port' and a[1] != '':
        db_port = a[1]
        options.remove(a)
        break


def disable_inherit_unported_modules(conn, cr):
    print("""defuse inheriting views originating from
    not yet ported modules""")
    cr.execute("""
        UPDATE ir_ui_view
        SET arch_db='<data/>'
        WHERE id in (
            SELECT iuv.id
            FROM ir_ui_view as iuv
            INNER JOIN ir_model_data as imd
            ON iuv.id = imd.res_id
            INNER JOIN ir_module_module as imm
            ON imd.module = imm.name
            WHERE imm.state <> 'installed'
            AND imd.model = 'ir.ui.view')
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


def partner_statement_config_settings(conn, cr):
    print("""fill default config settings for partner_statement""")

    # groups
    cr.execute(
        """SELECT res_id FROM ir_model_data WHERE module = 'account'
        AND model = 'res.groups' AND name = 'group_account_invoice'""")
    account_invoice_group_id = cr.fetchone()[0]
    cr.execute(
        """SELECT res_id FROM ir_model_data WHERE module = 'partner_statement'
        AND model = 'res.groups' AND name = 'group_activity_statement'""")
    activity_statement_group_id = cr.fetchone()[0]
    cr.execute(
        """SELECT res_id FROM ir_model_data WHERE module = 'partner_statement'
        AND model = 'res.groups' AND name = 'group_outstanding_statement'""")
    outstanding_statement_group_id = cr.fetchone()[0]
    cr.execute(
        """
        INSERT INTO res_groups_implied_rel (gid, hid)
        VALUES (%s, %s), (%s, %s)
    """, (account_invoice_group_id, activity_statement_group_id,
          account_invoice_group_id, outstanding_statement_group_id),
    )

    # defaults
    values = {
        'aging_type': json.dumps("days", ensure_ascii=False),
        'show_aging_buckets': json.dumps(True, ensure_ascii=False),
        'filter_partners_non_due': json.dumps(False, ensure_ascii=False),
        'filter_negative_balances': json.dumps(False, ensure_ascii=False),
    }
    cr.execute(
        """SELECT idef.id, imf.name
        FROM ir_default idef
        JOIN ir_model_fields imf ON idef.field_id = imf.id
        WHERE imf.model IN ('statement.common.wizard',
        'activity.statement.wizard', 'outstanding.statement.wizard')""")
    defaults = [x for x in cr.fetchall()]
    if defaults:
        for default in defaults:
            cr.execute(
                """UPDATE ir_default
                SET json_value = %s
                WHERE field_id = %s""", (values[default[1]], default[0]))
    else:
        cr.execute(
            """SELECT id, name FROM ir_model_fields
            WHERE model IN ('statement.common.wizard',
            'activity.statement.wizard', 'outstanding.statement.wizard')
            AND name IN ('aging_type', 'show_aging_buckets',
            'filter_partners_non_due', 'filter_negative_balances')"""
        )
        fields = [x for x in cr.fetchall()]
        for field in fields:
            cr.execute(
                """
                INSERT INTO ir_default (field_id, json_value)
                VALUES (%s, %s)""", (field[0], values[field[1]]),
            )
    conn.commit()


def set_chatter_sided_for_all(conn, cr):
    """Set chatter at the side of the screen for all users as it is the
    preferred setting.
    Reference ticket: #22512.
    """
    cr.execute("""
        UPDATE res_users
        SET chatter_position = 'sided'
        WHERE chatter_position <> 'sided';
    """)
    conn.commit()


def re_do_rename_for_unit_uom(conn, cr):
    """Rename UoM "Unit" to "PCE" as it was in v11.
    Reference ticket: #22238.
    """
    cr.execute("""
        UPDATE uom_uom
        SET name = 'PCE'
        WHERE id = 1;
    """)
    conn.commit()


def set_request_unit_to_hours(conn, cr):
    """Change request unit from day default to hours."""
    cr.execute("""
        UPDATE hr_leave_type
        SET request_unit = 'hour';
    """)
    conn.commit()


def main():
    # Define our connection string
    if db_password:
        conn_string = """dbname=%s user=%s password=%s""" % (
            db_name, db_user, db_password)
    else:
        conn_string = """dbname=%s user=%s""" % (db_name, db_user)

    if db_host:
        conn_string += """ host=%s""" % (db_host, )

    if db_port:
        conn_string += """ port=%s""" % (db_port, )

    # print the connection string we will use to connect
    print("Connecting to database\n	->%s", conn_string)

    # get a connection, if a connect cannot be made an exception
    # will be raised here
    conn = psycopg2.connect(conn_string)

    # conn.cursor will return a cursor object, you can use this cursor
    # to perform queries
    cr = conn.cursor()
    print("Connected!\n")

    disable_inherit_unported_modules(conn, cr)
    set_not_ported_modules_to_installed(conn, cr)
    partner_statement_config_settings(conn, cr)
    set_chatter_sided_for_all(conn, cr)
    re_do_rename_for_unit_uom(conn, cr)
    set_request_unit_to_hours(conn, cr)


if __name__ == "__main__":
    main()
