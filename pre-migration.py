#!/usr/bin/python
import psycopg2
import sys, getopt


def help_message():
    print '''pre-migration.py -- uses getopt to recognize options
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


def pre_install_modules(cr):
    cr.execute("""
        SELECT id
        FROM ir_module_module
        WHERE name='database_cleanup'""")
    if cr.fetchall():
        return
    cr.execute("""
        INSERT INTO ir_module_module (name, state)
        VALUES ('database_cleanup', 'to install')
    """)

    cr.execute("""
        SELECT id
        FROM ir_module_module
        WHERE name='base_technical_features'""")
    if cr.fetchall():
        return
    cr.execute("""
        INSERT INTO ir_module_module (name, state)
        VALUES ('base_technical_features', 'to install')
    """)


def delete_old_mail_group(cr):
    cr.execute("""
        DELETE FROM mail_followers
        WHERE res_model = 'mail.group'
        AND res_id NOT IN (select id from
        mail_group)
    """)


def delete_mail_catchall_alias(cr):
    """Delete mail.catchall.alias parameter, because it fails
    when module  mail is installed"""
    cr.execute("""
        DELETE FROM ir_config_parameter
        WHERE key = 'mail.catchall.alias'
    """)


def update_periods(cr):
    print("""Update Period 12/2013 to set is as a non-opening/closing
    period.""")

    cr.execute("""
        UPDATE account_period
        SET special = False
        WHERE name='12/2013'
    """)


def move_normal_moves_from_special_periods(cr):
    """The account migration script will delete all moves that are in the
    special periods. We need to remove any moves that are not created as
    opening balances for the opening period, so that they are not deleted."""

    print("""Selecting all the account moves that are in special periods,
    but not in a centralized journal.""")
    cr.execute("""
        SELECT am.id, am.name
        FROM account_move AS am
        INNER JOIN account_period AS ap
        ON ap.id = am.period_id
        INNER JOIN account_journal AS aj
        ON aj.id = am.journal_id
        WHERE ap.special=True
        AND aj.code NOT IN ('FY', 'OC11')
    """)
    move_ids = []
    for move_id, move_name in cr.fetchall():
        move_ids.append(move_id)
        print("""Move %s will be moved to another period""" % (move_name,))

    if move_ids:
        print("""Updating all previously selected moves to a new non special
        period within the move date.""")
        cr.execute("""
            UPDATE account_move as am
            SET period_id = ap.id
            FROM account_period AS ap
            WHERE am.id in %s
            AND ap.date_start <= am.date
            AND ap.date_stop >= am.date
            AND ap.special = False
        """, (tuple(move_ids),))


def update_invoice_uom(cr):
    print("""Updating the invoice lines to
    have the same uom as the order lines, if the category differs.""")

    cr.execute("""
        WITH Q AS (
                SELECT ail.id, sol.product_uom as uos_id
                FROM sale_order_line_invoice_rel as solinvl
                INNER JOIN sale_order_line as sol
                ON sol.id = solinvl.order_line_id
                INNER JOIN account_invoice_line as ail
                ON ail.id = solinvl.invoice_id
                INNER JOIN product_uom puom1
                ON puom1.id = sol.product_uom
                INNER JOIN product_uom_categ poc1
                ON poc1.id = puom1.category_id
                INNER JOIN product_uom puom2
                ON puom2.id = ail.uos_id
                INNER JOIN product_uom_categ poc2
                ON poc2.id = puom2.category_id
                WHERE poc2.id != poc1.id
        )
        UPDATE account_invoice_line
        SET uos_id = Q.uos_id
        FROM Q
        WHERE account_invoice_line.id = Q.id
    """)
    print ("Rows affected: %s" % cr.rowcount)


def uninstall_modules(cr):
    print("""Uninstalling modules: crm_phone, base_phone """)

    cr.execute("""UPDATE ir_module_module SET state='uninstalled'
    WHERE name in ('crm_phone', 'base_phone')""")
    print ("Rows affected: %s" % cr.rowcount)


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

    pre_install_modules(cr)
    delete_old_mail_group(cr)
    delete_mail_catchall_alias(cr)
    update_periods(cr)
    move_normal_moves_from_special_periods(cr)
    update_invoice_uom(cr)
    uninstall_modules(cr)

    # Commit all changes
    conn.commit()

if __name__ == "__main__":
    main()
