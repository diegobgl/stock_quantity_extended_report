from odoo import models, fields, api, tools

class StockQuantityHistoryExtended(models.TransientModel):
    _inherit = 'stock.quantity.history'

    location_id = fields.Many2one('stock.location', string="Ubicación", domain="[('usage', 'in', ['internal', 'transit'])]")

    def open_at_date(self):
        active_model = self.env.context.get('active_model')
        if active_model == 'stock.valuation.layer':
            action = self.env["ir.actions.actions"]._for_xml_id("stock_account.stock_valuation_layer_action")

            # Obtener vistas
            tree_view = self.env.ref('stock_account.stock_valuation_layer_valuation_at_date_tree_inherited', raise_if_not_found=False)
            graph_view = self.env.ref('stock_account.stock_valuation_layer_graph', raise_if_not_found=False)

            # Configuración de vistas en la acción
            action['views'] = [
                (tree_view.id if tree_view else False, 'tree'),
                (self.env.ref('stock_account.stock_valuation_layer_form').id, 'form'),
                (self.env.ref('stock_account.stock_valuation_layer_pivot').id, 'pivot'),
                (graph_view.id if graph_view else False, 'graph')
            ]

            # Configuración del dominio
            domain = [('create_date', '<=', self.inventory_datetime), ('product_id.type', '=', 'product')]
            if self.location_id:
                domain.append(('location_id', '=', self.location_id.id))

            action['domain'] = domain
            action['display_name'] = format_datetime(self.env, self.inventory_datetime)
            action['context'] = "{}"
            return action

        return super(StockQuantityHistoryExtended, self).open_at_date()



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
        tools.drop_view_if_exists(self._cr, 'report_stock_quantity_extended')
        query = """
            CREATE or REPLACE VIEW report_stock_quantity_extended AS (
                SELECT
                    MIN(svl.id) AS id,
                    svl.product_id,
                    svl.company_id,
                    COALESCE(sm.location_id, sq.location_id) AS location_id,
                    pt.default_code AS product_reference,
                    pt.name AS product_name,
                    MAX(sm.date) AS last_movement_date,
                    CASE
                        WHEN po.id IS NOT NULL THEN 'purchase'
                        WHEN sm.location_id IS NOT NULL AND sm.location_dest_id IS NOT NULL THEN 'internal'
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
                    svl.product_id, svl.company_id, COALESCE(sm.location_id, sq.location_id), 
                    pt.default_code, pt.name, po.id, svl.unit_cost, sm.location_id, sm.location_dest_id
            )
        """
        self.env.cr.execute(query)

class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

    location_id = fields.Many2one('stock.location', string="Location", compute='_compute_location_id', store=True)

    @api.depends('stock_move_id')
    def _compute_location_id(self):
        for svl in self:
            if svl.stock_move_id:
                svl.location_id = svl.stock_move_id.location_id
            else:
                svl.location_id = False

