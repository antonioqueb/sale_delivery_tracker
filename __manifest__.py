{
    'name': 'Sale Delivery Tracker',
    'version': '19.0.1.0.0',
    'category': 'Sales',
    'summary': 'Track delivery status directly from Sale Orders with visual indicators',
    'description': """
        Shows the last relevant delivery document per flow in the sale order,
        with a visual progress indicator showing delivery stages and quantities.
        Supports multi-step delivery (Pick → Pack → Ship) and partial deliveries.
    """,
    'author': 'Alphaqueb Consulting',
    'website': 'https://www.alphaqueb.com',
    'depends': ['sale_stock', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sale_delivery_tracker/static/src/css/delivery_tracker.css',
            'sale_delivery_tracker/static/src/js/delivery_tracker.js',
            'sale_delivery_tracker/static/src/xml/delivery_tracker.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
