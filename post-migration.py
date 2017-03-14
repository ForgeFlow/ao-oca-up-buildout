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
        SET arch='<data/>',
        arch_db='<data/>'
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


def deactivate_features(conn, cr):
    print("""deactivate cronjobx, mailservers, fetchmail""")

    cr.execute("""DELETE FROM ir_mail_server""")
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


def remove_account_analytic_analysis(conn, cr):
    print("""Get rid of message: Could not get content for
    /account_analytic_analysis/static/css/analytic.css defined in bundle
    'web.assets_backend'
    """)
    cr.execute("""
        DELETE FROM ir_ui_view v
        WHERE name = 'account_analytic_analysis assets'
    """)
    conn.commit()


def update_product_category(conn, cr):
    print("""Pre-create default values for product categories (costing
    method and inventory valuation)""")

    # Select the field_id
    cr.execute("""
    SELECT imf.id
    FROM ir_model_fields as imf
    INNER JOIN ir_model as im
    ON imf.model_id = im.id
    WHERE im.name = 'Product Category'
    AND imf.name = 'property_cost_method'
    """)
    costing_method_field_id = cr.fetchone()[0] or False

    # Select the field_id
    cr.execute("""
    select imf.id
    from ir_model_fields as imf
    inner join ir_model as im
    on imf.model_id = im.id
    where im.name = 'Product Category'
    and imf.name = 'property_valuation'
    """)
    valuation_field_id = cr.fetchone()[0] or False

    # Select the product categories
    cr.execute("""
    SELECT id
    FROM product_category
    """)

    for categ_id, in cr.fetchall():
        cr.execute("""
        INSERT INTO ir_property (value_text,name,create_uid,type,
        company_id,write_uid,fields_id,res_id,create_date,write_date)
        VALUES ('real','property_cost_method',1,'selection',1,1,%s,
        'product.category,%s',now(),now())
        """ % (costing_method_field_id, categ_id))

        cr.execute("""
        INSERT INTO ir_property (value_text,name,create_uid,type,
        company_id,write_uid,fields_id,res_id,create_date,write_date)
        VALUES ('real_time','property_valuation',1,'selection',1,1,%s,
        'product.category,%s',now(),now())
        """ % (valuation_field_id, categ_id))


def update_payments_from_vouchers(conn, cr):
    """Update account.payment rows from corresponding account.voucher rows."""
    # Use the fact that id of migrated account_payment is id of original
    # account_voucher.
    # Do not set: check_number = av.number
    # new check_number is integer value, av.number was text filled from
    # sequence.
    print("""Update payments from vouchers'""")
    cr.execute(
        """\
        UPDATE account_payment ap
        SET
            check_number = CAST(av.check_number AS INTEGER)
        FROM account_voucher av
        WHERE ap.id = av.id
        """
    )
    conn.commit()


def update_subcontracted_service(conn, cr):
    """Update the subcontracted service"""
    print("""Update subcontracted service'""")

    # Select the field_id
    cr.execute("""
    select imf.id
    from ir_model_fields as imf
    inner join ir_model as im
    on imf.model_id = im.id
    where im.name = 'Product Template'
    and imf.name = 'property_subcontracted_service'
    """)

    subontracted_service_field_id = cr.fetchone()[0] or False

    cr.execute("""
        SELECT product_tmpl_id
        FROM product_product
        WHERE default_code IN ('SR-MN0001', 'SR-MN0002', 'SR-MN0003',
        'SR-MN0004', 'SR-MN0005', 'SR-MN0006')
    """)
    for template_id, in cr.fetchall():
        cr.execute("""
        INSERT INTO ir_property (value_integer,name,create_uid,type,
        company_id,write_uid,fields_id,res_id,create_date,write_date)
        VALUES (1,'property_subcontracted_service',1,'boolean',1,1,%s,
        'product.template,%s',now(),now())
        """ % (subontracted_service_field_id, template_id))

    conn.commit()


def delete_views(conn, cr):
    print("""Get rid of an old analytic account view'""")

    # analytic account view
    cr.execute("""
        DELETE
        from ir_ui_view
        where inherit_id = 1940
    """)
    cr.execute("""
        DELETE
        from ir_ui_view
        where id = 1940
    """)

    # Stock move
    cr.execute("""
        DELETE
        from ir_ui_view
        where inherit_id = 2028
    """)

    cr.execute("""
        DELETE
        from ir_ui_view
        where id = 2028
    """)

    # View `account.voucher.receipt.form`
    cr.execute("""
        DELETE
        from ir_ui_view
        where inherit_id = 606
    """)

    cr.execute("""
        DELETE
        from ir_ui_view
        where id = 606
    """)

    # View `account.move.line tree_account_reconciliation`
    cr.execute("""
        DELETE
        from ir_ui_view
        where inherit_id = 1937
    """)

    cr.execute("""
        DELETE
        from ir_ui_view
        where id = 1937
    """)

    # View `account.move.form.inherit`
    # [view_id: 1555, xml_id: account_analytic_plans.view_move_form_inherit,
    # model: account.move, parent_id: 360]
    cr.execute("""
        DELETE
        from ir_ui_view
        where inherit_id = 1555
    """)

    cr.execute("""
        DELETE
        from ir_ui_view
        where id = 1555
    """)

    # Error context:
    # View `account.analytic.line.tree`
    # [view_id: 455, xml_id: n/a, model: account.analytic.line, parent_id: n/a]
    cr.execute("""
        DELETE
        from ir_ui_view
        where inherit_id = 455
    """)

    cr.execute("""
        DELETE
        from ir_ui_view
        where id = 455
    """)

    # Error context:
    # View `account.analytic.line.form`
    # [view_id: 454, xml_id: n / a, model: account.analytic.line, parent_id:
    # n / a]
    cr.execute("""
        DELETE
        from ir_ui_view
        where inherit_id = 454
    """)

    cr.execute("""
        DELETE
        from ir_ui_view
        where id = 454
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
#    reset_all_users_passwords(conn, cr)
    remove_account_analytic_analysis(conn, cr)
    update_product_category(conn, cr)
    update_payments_from_vouchers(conn, cr)
    update_subcontracted_service(conn, cr)
    delete_views(conn, cr)


if __name__ == "__main__":
    main()
