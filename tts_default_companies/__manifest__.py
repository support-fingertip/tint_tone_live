{
    'name': 'Default Enabled Companies',
    'version': '1.0',
    'category': 'Administration',
    'summary': 'Configure default enabled companies for users on login',
    'description': """
        This module allows administrators to configure a set of Default Enabled Companies
        for each user. When the user logs in, these companies are automatically activated
        in their web session.
    """,
    'author': 'Tint Tone',
    'depends': ['base', 'web'],
    'data': [
        'views/res_users_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
