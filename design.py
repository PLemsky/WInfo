# projekt_gpx_viewer/design.py
from nicegui import ui, app # app importieren für app.storage.user
from typing import Optional

PRIMARY_COLOR_HEX = '#1B5E20'
SECONDARY_COLOR_HEX = '#A5D6A7'
BACKGROUND_COLOR_HEX = '#E8F5E9'
TEXT_COLOR_HEX = '#1B2E23'

def apply_design_and_get_header():
    ui.add_head_html(f"""
    <style>
        :root {{
            --color-primary: {PRIMARY_COLOR_HEX};
            --color-secondary: {SECONDARY_COLOR_HEX};
            --color-background: {BACKGROUND_COLOR_HEX};
            --color-text: {TEXT_COLOR_HEX};
        }}
        body {{
            background-color: var(--color-background) !important;
            color: var(--color-text) !important;
            font-family: 'Roboto', -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        }}
        .btn-custom-primary {{
            background-color: var(--color-primary) !important;
            color: white !important;
        }}
        .btn-custom-primary:hover {{
            filter: brightness(1.15);
        }}
    </style>
    """)
    ui.colors(primary=PRIMARY_COLOR_HEX,
              secondary=SECONDARY_COLOR_HEX,
              accent=PRIMARY_COLOR_HEX,
              positive='#2E7D32',
              negative='#C62828',
              info='#0277BD',
              warning='#FF8F00')

    async def handle_logout():
        app.storage.user.pop('authenticated_user_id', None)
        app.storage.user.pop('authenticated_username', None)
        ui.navigate.to('/login')
        ui.notify('Erfolgreich ausgeloggt.', type='positive')

    def app_header():
        with ui.header(elevated=True).style(f'background-color: {PRIMARY_COLOR_HEX};').classes('items-center justify-between text-white q-py-sm q-px-md'):
            with ui.row().classes('items-center'):
                ui.icon('route', size='lg').classes('q-mr-sm')
                ui.label('GPX Track Manager').classes('text-h5 font-bold')
            
            with ui.row().classes('items-center'):
                # Zugriff auf app.storage.user, um den Zustand zu prüfen
                authenticated_username = app.storage.user.get('authenticated_username')
                if authenticated_username:
                    ui.label(f'Angemeldet als: {authenticated_username}').classes('q-mr-md')
                    ui.button('Logout', on_click=handle_logout).props('flat color=white')
                else:
                    # Auf Login/Register-Seiten wird kein Login-Button benötigt,
                    # aber auf geschützten Seiten wäre hier ein Fallback denkbar.
                    # Da der Header nur auf der Hauptseite (geschützt) oder Login/Register (nicht geschützt)
                    # gerendert wird, ist dies hier meist nicht sichtbar, wenn nicht eingeloggt.
                    pass

    return app_header