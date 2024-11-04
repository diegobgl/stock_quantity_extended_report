from odoo import models, fields, tools

class StockQuantityHistoryExtended(models.TransientModel):
    _inherit = 'stock.quantity.history'

    location_id = fields.Many2one('stock.location', string="Ubicación", domain="[('usage', 'in', ['internal', 'transit'])]")

    def open_at_date(self):
        # Llamamos al método original
        result = super(StockQuantityHistoryExtended, self).open_at_date()
        
        # Extendemos el contexto para incluir el campo de ubicación si está especificada
        if self.location_id:
            result['context'] = dict(result.get('context', {}), location_id=self.location_id.id)

        return result


class ReportStockQuantityExtended(models.Model):
    _inherit = 'report.stock.quantity'

    location_id = fields.Many2one('stock.location', string='Ubicación', readonly=True)
    product_reference = fields.Char(string='Referencia Interna', readonly=True)
    product_name = fields.Char(string='Nombre de Producto', readonly=True)
    lot_id = fields.Many2one('stock.production.lot', string='Lote/Número de Serie', readonly=True)
    last_movement_date = fields.Datetime(string='Fecha Último Movimiento', readonly=True)
    movement_type = fields.Selection([('purchase', 'Compra'), ('internal', 'Transferencia Interna')], string='Tipo Movimiento', readonly=True)
    quantity = fields.Float('Cantidad', readonly=True)
    unit_value = fields.Float('Valor Unitario', readonly=True)
    total_value = fields.Float('Valorizado', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self._cr, 'report_stock_quantity')
        query = """
            CREATE or REPLACE VIEW report_stock_quantity AS (
                SELECT
                    MIN(svl.id) AS id,
                    svl.product_id,
                    svl.company_id,
                    sq.location_id,
                    pt.default_code AS product_reference,
                    pt.name AS product_name,
                    MAX(sm.date) AS last_movement_date,
                    CASE
                        WHEN po.id IS NOT NULL THEN 'purchase'
                        WHEN sm.location_id.usage = 'internal' AND sm.location_dest_id.usage = 'internal' THEN 'internal'
                    END AS movement_type,
                    SUM(svl.quantity) AS quantity,
                    svl.unit_cost AS unit_value,
                    SUM(svl.quantity * svl.unit_cost) AS total_value
                FROM
                    stock_valuation_layer svl
                LEFT JOIN
                    stock_quant sq ON sq.product_id = svl.product_id
                LEFT JOIN
                    stock_move sm ON sm.id = svl.stock_move_id
                LEFT JOIN
                    product_product pp ON pp.id = svl.product_id
                LEFT JOIN
                    product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN
                    purchase_order_line pol ON pol.id = sm.purchase_line_id
                LEFT JOIN
                    purchase_order po ON po.id = pol.order_id
                WHERE
                    svl.create_date <= (now() at time zone 'utc')::date
                GROUP BY
                    svl.product_id, svl.company_id, sq.location_id, pt.default_code, pt.name, po.id, sm.location_id.usage, sm.location_dest_id.usage, svl.unit_cost
            )
        """
        self.env.cr.execute(query)

