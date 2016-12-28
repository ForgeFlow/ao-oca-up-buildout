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


def pre_install_modules(conn, cr):
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


def delete_old_mail_group(conn, cr):
    try:
        cr.execute("""
            DELETE FROM mail_followers
            WHERE res_model = 'mail.group'
            AND res_id NOT IN (select id from
            mail_group)
        """)
    except psycopg2.ProgrammingError:
        # If query fails it is because the table 'mail_group' is no longer
        # defined.
        return
    conn.commit()


def delete_mail_catchall_alias(conn, cr):
    """Delete mail.catchall.alias parameter, because it fails
    when module  mail is installed"""

    try:
        cr.execute("""
        DELETE FROM ir_config_parameter
        WHERE key = 'mail.catchall.alias'
    """)

    except psycopg2.InternalError:
        # If query fails ignore
        return
    conn.commit()


def update_periods(conn, cr):
    print("""Update Period 12/2013 to set is as a non-opening/closing
    period.""")

    try:
        cr.execute("""
            UPDATE account_period
            SET special = False
            WHERE name='12/2013'
        """)
    except psycopg2.InternalError:
        # If query fails ignore
        return
    conn.commit()


def move_normal_moves_from_special_periods(conn, cr):
    """The account migration script will delete all moves that are in the
    special periods. We need to remove any moves that are not created as
    opening balances for the opening period, so that they are not deleted."""

    print("""Selecting all the account moves that are in special periods,
    but not in a centralized journal.""")
    try:
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
    except psycopg2.InternalError:
        # If query fails ignore
        return
    conn.commit()

    move_ids = []
    for move_id, move_name in cr.fetchall():
        move_ids.append(move_id)
        print("""Move %s will be moved to another period""" % (move_name,))

    if move_ids:
        print("""Updating all previously selected moves to a new non special
        period within the move date.""")
        try:
            cr.execute("""
                UPDATE account_move as am
                SET period_id = ap.id
                FROM account_period AS ap
                WHERE am.id in %s
                AND ap.date_start <= am.date
                AND ap.date_stop >= am.date
                AND ap.special = False
            """, (tuple(move_ids),))
        except psycopg2.InternalError:
            # If query fails ignore
            return
        conn.commit()


def update_sale_invoice_uom(conn, cr):
    print("""Updating the UoM invoice lines to
    have the same uom as the sales order lines, if the category differs.""")

    try:
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
    except psycopg2.InternalError:
        # If query fails ignore
        return
    conn.commit()
    print ("Rows affected: %s" % cr.rowcount)


def update_sale_stock_uom(conn, cr):
    print("""Updating the UoM in stock moves to
    have the same uom as the sales order lines, if the category differs.""")

    try:
        cr.execute("""
            WITH Q AS (
                SELECT sm.id, sol.product_uom as uom_id
                FROM stock_move as sm
                INNER JOIN procurement_order as pr
                ON pr.id = sm.procurement_id
                INNER JOIN sale_order_line as sol
                ON pr.sale_line_id = sol.id
                INNER JOIN product_uom puom1
                ON puom1.id = sol.product_uom
                INNER JOIN product_uom_categ poc1
                ON poc1.id = puom1.category_id
                INNER JOIN product_uom puom2
                ON puom2.id = sm.product_uom
                INNER JOIN product_uom_categ poc2
                ON poc2.id = puom2.category_id
                WHERE poc2.id != poc1.id
            )
            UPDATE stock_move
            SET product_uom = Q.uom_id
            FROM Q
            WHERE stock_move.id = Q.id
        """)
    except psycopg2.InternalError:
        # If query fails ignore
        return
    conn.commit()
    print ("Rows affected: %s" % cr.rowcount)


def update_purchase_stock_uom(conn, cr):
    print("""Updating the UoM in stock moves to
    have the same uom as the purchase order lines, if the category differs.""")

    try:
        cr.execute("""
            WITH Q AS (
                SELECT sm.id, pol.product_uom as uom_id
                FROM stock_move as sm
                INNER JOIN purchase_order_line as pol
                ON pol.id = sm.purchase_line_id
                INNER JOIN product_uom puom1
                ON puom1.id = pol.product_uom
                INNER JOIN product_uom_categ poc1
                ON poc1.id = puom1.category_id
                INNER JOIN product_uom puom2
                ON puom2.id = sm.product_uom
                INNER JOIN product_uom_categ poc2
                ON poc2.id = puom2.category_id
                WHERE poc2.id != poc1.id
            )
            UPDATE stock_move
            SET product_uom = Q.uom_id
            FROM Q
            WHERE stock_move.id = Q.id
        """)
    except psycopg2.InternalError:
        # If query fails ignore
        return
    conn.commit()
    print ("Rows affected: %s" % cr.rowcount)


def update_purchase_invoice_uom(conn, cr):
    print("""Updating the UoM in invoice lines to
    have the same uom as the purchase order lines, if the category differs.""")

    try:
        cr.execute("""
            WITH Q AS (
                    SELECT ail.id, pol.product_uom as uom_id
                    FROM purchase_order_line_invoice_rel as polinvl
                    INNER JOIN purchase_order_line as pol
                    ON pol.id = polinvl.order_line_id
                    INNER JOIN account_invoice_line as ail
                    ON ail.id = polinvl.invoice_id
                    INNER JOIN product_uom puom1
                    ON puom1.id = pol.product_uom
                    INNER JOIN product_uom_categ poc1
                    ON poc1.id = puom1.category_id
                    INNER JOIN product_uom puom2
                    ON puom2.id = ail.uos_id
                    INNER JOIN product_uom_categ poc2
                    ON poc2.id = puom2.category_id
                    WHERE poc2.id != poc1.id
            )
            UPDATE account_invoice_line
            SET uos_id = Q.uom_id
            FROM Q
            WHERE account_invoice_line.id = Q.id
        """)
    except psycopg2.InternalError:
        # If query fails ignore
        return
    conn.commit()
    print ("Rows affected: %s" % cr.rowcount)


def delete_account_analytic_analysis_backend_view(conn, cr):
    print("""Deleting the assets backend from account_analytic_analysis""")
    try:
        cr.execute("""
            DELETE
            FROM
            ir_ui_view
            where
            name = 'account_analytic_analysis assets'
        """)
    except psycopg2.InternalError:
        # If query fails ignore
        return
    conn.commit()
    print ("Rows affected: %s" % cr.rowcount)


def update_account_tax(conn, cr):
    print("""Updating the only account.tax record associated to python code,
    field python_applicable """)
    try:
        cr.execute("""
            UPDATE account_tax
            SET python_applicable = 'result = True'
            WHERE
            id = 33
        """)
    except psycopg2.InternalError:
        # If query fails ignore
        return
    conn.commit()
    print ("Rows affected: %s" % cr.rowcount)

    print("""Updating the only account.tax record associated to python code,
    field python_compute""")
    try:
        cr.execute("""
            UPDATE account_tax
            SET python_compute = 'result = price_unit'
            WHERE
            id = 33
        """)
    except psycopg2.InternalError:
        # If query fails ignore
        return
    conn.commit()
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

    pre_install_modules(conn, cr)
    delete_old_mail_group(conn, cr)
    delete_mail_catchall_alias(conn, cr)
    update_periods(conn, cr)
    move_normal_moves_from_special_periods(conn, cr)
    update_sale_invoice_uom(conn, cr)
    update_sale_stock_uom(conn, cr)
    update_purchase_stock_uom(conn, cr)
    update_purchase_invoice_uom(conn, cr)
    delete_account_analytic_analysis_backend_view(conn, cr)
    update_account_tax(conn, cr)

if __name__ == "__main__":
    main()
