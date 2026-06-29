{
    'name': 'TTS Ask AI Config',
    'version': '1.0',
    'category': 'Customizations',
    'summary': 'Toggle Ask AI Systray Icon',
    'description': """
This module provides a configuration option to toggle the visibility of the "Ask AI" icon in the systray.
    """,
    'depends': ['base', 'web', 'ai'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'tts_ask_ai_config/static/src/js/systray_ai_patch.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
