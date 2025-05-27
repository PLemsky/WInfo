from nicegui import ui, app
from typing import Optional, Any 
import traceback
from types import SimpleNamespace 


import db_config 

PRIMARY_COLOR_HEX = '#1B5E20'
SECONDARY_COLOR_HEX = '#A5D6A7'
BACKGROUND_COLOR_HEX = '#E8F5E9'
TEXT_COLOR_HEX = '#1B2E23'

def apply_design_and_get_header():
    ui.add_head_html(f"""
    <style>
        /* ... styles ... */
    </style>
    """)
    ui.colors(primary=PRIMARY_COLOR_HEX, secondary=SECONDARY_COLOR_HEX, 
              accent=PRIMARY_COLOR_HEX, positive='#2E7D32', negative='#C62828',
              info='#0277BD', warning='#FF8F00')

    async def handle_logout():
        # ... (logout logic) ...
        user_keys_to_clear = [
            'authenticated_user_id', 'authenticated_username',
            'tracks_in_table_data', 'selected_track_ids_list',
            'filter_date_from_str', 'filter_date_to_str',
            'filter_labels_list', 'map_needs_initial_fit',
            'pending_2fa_user_id_for_email'
        ]
        for key in user_keys_to_clear:
            app.storage.user.pop(key, None)
        
        client_keys_to_clear = [
            'ui_map_view', 'ui_track_table', 'ui_stats_dist', 'ui_stats_asc',
            'ui_elevation_chart_container', 'ui_label_select_filter', 'manage_2fa_button'
        ]
        for key in client_keys_to_clear:
            if key in app.storage.client:
                del app.storage.client[key]
        ui.navigate.to('/login')
        ui.notify('Erfolgreich ausgeloggt.', type='positive')


    async def manage_email_2fa_dialog_logic():
        current_user_id = app.storage.user.get('authenticated_user_id')
        if not current_user_id:
            ui.notify("Nicht eingeloggt.", type='warning')
            return

        dialog_state = SimpleNamespace()
        dialog_state.dialog_instance = None 
        dialog_state.status_label = None   
        dialog_state.action_button = None  
        dialog_state.is_2fa_currently_enabled = False 

        db_s_init = None
        try:
            db_s_init = db_config.SessionLocal()
            user = db_config.get_user_by_id(db_s_init, current_user_id)
            if not user:
                ui.notify("Benutzer nicht gefunden.", type='error')
                return
            if not user.email:
                 ui.notify("Keine E-Mail-Adresse für diesen Account hinterlegt. 2FA nicht möglich.", type='warning')
                 return
            dialog_state.is_2fa_currently_enabled = user.is_2fa_enabled
        finally:
            if db_s_init: db_s_init.close()

        async def update_dialog_ui_inner():
            db_s_update = None
            try:
                db_s_update = db_config.SessionLocal()
                user_update = db_config.get_user_by_id(db_s_update, current_user_id)
                if user_update:
                    dialog_state.is_2fa_currently_enabled = user_update.is_2fa_enabled
                    if dialog_state.status_label:
                        dialog_state.status_label.set_text(f"Status: {'Aktiviert' if dialog_state.is_2fa_currently_enabled else 'Deaktiviert'}")
                    if dialog_state.action_button:
                        dialog_state.action_button.set_text('E-Mail 2FA Deaktivieren' if dialog_state.is_2fa_currently_enabled else 'E-Mail 2FA Aktivieren')
                        dialog_state.action_button.props(remove='color=positive' if not dialog_state.is_2fa_currently_enabled else 'color=negative')
                        dialog_state.action_button.props(add='color=negative' if dialog_state.is_2fa_currently_enabled else 'color=positive')
                    
                    if manage_2fa_button_header_ref := app.storage.client.get('manage_2fa_button'):
                         manage_2fa_button_header_ref.set_text('2FA Verwalten (Aktiv)' if dialog_state.is_2fa_currently_enabled else '2FA Einrichten')
                else:
                     if dialog_state.dialog_instance: dialog_state.dialog_instance.close()
            finally:
                if db_s_update: db_s_update.close()


        async def toggle_2fa_status_inner():
            db_s_toggle = None
            try:
                db_s_toggle = db_config.SessionLocal()
                user_toggle = db_config.get_user_by_id(db_s_toggle, current_user_id)
                if not user_toggle or not user_toggle.email:
                    ui.notify("Benutzer oder E-Mail nicht gefunden. Aktion abgebrochen.", type='error')
                    if dialog_state.dialog_instance: dialog_state.dialog_instance.close()
                    return

                if dialog_state.is_2fa_currently_enabled:
                    if db_config.disable_email_2fa(db_s_toggle, current_user_id):
                        ui.notify("E-Mail 2FA erfolgreich deaktiviert.", type='positive')
                    else:
                        ui.notify("Fehler beim Deaktivieren der E-Mail 2FA.", type='negative')
                else:
                    if db_config.enable_email_2fa(db_s_toggle, current_user_id):
                        ui.notify("E-Mail 2FA erfolgreich aktiviert. Sie erhalten beim nächsten Login einen Code per E-Mail.", type='positive')
                    else:
                        ui.notify("Fehler beim Aktivieren der E-Mail 2FA.", type='negative')
                await update_dialog_ui_inner() 
            except Exception as e:
                print(f"Fehler beim Umschalten des 2FA Status: {e}")
                traceback.print_exc()
                ui.notify("Ein Fehler ist aufgetreten.", type="error")
            finally:
                if db_s_toggle: db_s_toggle.close()


        with ui.dialog().props("persistent") as temp_dialog_instance, ui.card().style("min-width: 350px; max-width: 450px"):
            dialog_state.dialog_instance = temp_dialog_instance
            ui.label("E-Mail Zwei-Faktor-Authentifizierung (2FA)").classes("text-h6")
            ui.separator()
            with ui.column().classes("w-full items-center gap-4 my-4"):
                dialog_state.status_label = ui.label() 
                dialog_state.action_button = ui.button(on_click=toggle_2fa_status_inner)
            ui.separator()
            ui.button("Schließen", on_click=lambda: dialog_state.dialog_instance.close() if dialog_state.dialog_instance else None).props("flat color=grey").classes("self-end mt-2")

        await update_dialog_ui_inner() 
        if dialog_state.dialog_instance:
            dialog_state.dialog_instance.open()
    
    def app_header():
        with ui.header(elevated=True).style(f'background-color: {PRIMARY_COLOR_HEX};').classes('items-center justify-between text-white q-py-sm q-px-md'):
            with ui.row().classes('items-center'):
                ui.icon('route', size='lg').classes('q-mr-sm')
                ui.label('GPX Track Manager').classes('text-h5 font-bold')
            
            with ui.row().classes('items-center'):
                authenticated_username = app.storage.user.get('authenticated_username')
                if authenticated_username:
                    ui.label(f'Angemeldet als: {authenticated_username}').classes('q-mr-md text-sm')
                    
                    manage_2fa_btn = ui.button(on_click=manage_email_2fa_dialog_logic).props('flat color=white outline dense').classes('q-mr-sm text-xs')
                    app.storage.client['manage_2fa_button'] = manage_2fa_btn
                    
                    async def update_2fa_button_text_on_load_header():
                        current_user_id_header = app.storage.user.get('authenticated_user_id')
                        if not current_user_id_header: return
                        
                        header_button_ref = app.storage.client.get('manage_2fa_button')
                        if not header_button_ref: return

                        db_s_header = None
                        is_enabled_header = False
                        try:
                            db_s_header = db_config.SessionLocal()
                            user_header = db_config.get_user_by_id(db_s_header, current_user_id_header)
                            is_enabled_header = user_header.is_2fa_enabled if user_header else False
                        finally:
                            if db_s_header: db_s_header.close()
                        
                        try:
                            header_button_ref.set_text('2FA Verwalten (Aktiv)' if is_enabled_header else '2FA Einrichten')
                        except Exception: 
                            pass 

                    ui.timer(0.2, update_2fa_button_text_on_load_header, once=True)

                    ui.button('Logout', on_click=handle_logout).props('flat color=white dense').classes('text-xs')
    return app_header