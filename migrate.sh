#!/bin/sh

DATABASE=$1

if [ -z "$DATABASE" ]; then
    echo I need a database
    exit 1
fi

pip install openupgradelib

psql $DATABASE -U odoo<<HEREDOC
--- Add here pre-migration SQL statements
--- Mark some modules for installation
insert into ir_module_module (name, state) values ('database_cleanup', 'to install');
insert into ir_module_module (name, state) values ('base_technical_features', 'to install');
HEREDOC

VERSIONS=$(eval echo bin/start_openupgrade*)
for version in $VERSIONS; do
    $version --db_user odoo --db_password commitment --update=all --stop-after-init --database=$DATABASE || exit 1
done

psql $DATABASE -U odoo <<HEREDOC
--- Add here post-migration SQL statements
--- *** those are temporary ***
--- defuse inheriting views originating from not yet ported modules
update ir_ui_view set arch='<data/>' from ir_model_data join ir_module_module on ir_model_data.module=ir_module_module.name where ir_model_data.model='ir.ui.view' and res_id=ir_ui_view.id and inherit_id is not null and ir_module_module.state <> 'installed';
--- set not yet ported modules to installed (otherwise, updating a module to work on becomes tricky)
update ir_module_module set state='installed' where state in ('to install', 'to upgrade');
--- deactivate cronjobx, mailservers, fetchmail
delete from ir_mail_server;
update fetchmail_server set active=False;
update ir_cron set active=False;
--- reset all user passwords
update res_users set password_crypt=(select password_crypt from res_users where login='admin');
--- *** those need to be kept ***

HEREDOC

