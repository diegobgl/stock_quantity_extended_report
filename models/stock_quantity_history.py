from odoo import models, fields, api, _
from odoo.tools.misc import format_datetime
from odoo.osv import expression
import logging



class StockQuantityHistoryExtended(models.TransientModel):
    _inherit = 'stock.quantity.history'

    location_id = fields.Many2one(
        'stock.location', string="Ubicación",
        domain="[('usage', 'in', ['internal', 'transit'])]"
    )

    def open_detailed_view(self):
        """
        Consulta alternativa que utiliza stock.quants para mostrar productos, ubicaciones y lotes.
        """
        tree_view_id = self.env.ref('stock.view_stock_quant_tree').id  # Vista original de stock.quant

        domain = [('product_id.type', '=', 'product')]
        if self.inventory_datetime:
            domain.append(('in_date', '<=', self.inventory_datetime))  # Filtra por fecha
        if self.location_id:
            domain.append(('location_id', '=', self.location_id.id))  # Filtra por ubicación si está especificada

        action = {
            'type': 'ir.actions.act_window',
            'name': _('Detailed Product Quantities'),
            'res_model': 'stock.quant',
            'view_mode': 'tree',
            'views': [(tree_view_id, 'tree')],
            'domain': domain,
            'context': dict(self.env.context, to_date=self.inventory_datetime),
        }
        return action


    def open_at_date(self):
        """
        Abre la vista en 'stock.valuation.layer' mostrando solo registros con asientos contables relacionados.
        """
        active_model = self.env.context.get('active_model')

        if active_model == 'stock.valuation.layer':
            # Obtener la acción original
            action = self.env["ir.actions.actions"]._for_xml_id("stock_account.stock_valuation_layer_action")

            # Configuración de vistas
            tree_view = self.env.ref('stock_account.view_stock_valuation_layer_tree', raise_if_not_found=False)
            form_view = self.env.ref('stock_account.stock_valuation_layer_form', raise_if_not_found=False)
            pivot_view = self.env.ref('stock_account.stock_valuation_layer_pivot', raise_if_not_found=False)

            action['views'] = [
                (tree_view.id if tree_view else False, 'tree'),
                (form_view.id if form_view else False, 'form'),
                (pivot_view.id if pivot_view else False, 'pivot')
            ]

            # Crear un dominio para filtrar solo los registros con movimientos asociados a asientos contables
            domain = [
                ('create_date', '<=', self.inventory_datetime),
                ('product_id.type', '=', 'product'),
                ('account_move_id', '!=', False)  # Filtrar registros con asiento contable
            ]
            if self.location_id:
                domain.append(('location_id', '=', self.location_id.id))

            action['domain'] = domain
            action['display_name'] = _("Valuation Layers with Accounting Entries")
            action['context'] = {
                "to_date": self.inventory_datetime
            }

            return action

        # Comportamiento original si no es 'stock.valuation.layer'
        return super(StockQuantityHistoryExtended, self).open_at_date()



class ProductProduct(models.Model):
    _inherit = 'product.product'

    location_ids = fields.Many2many(
         'stock.location', string='Ubicaciones',
         compute='_compute_location_ids', store=False
     )

    lot_ids = fields.Many2many(
         'stock.lot', string='Lotes Disponibles',
         compute='_compute_lot_ids', store=False
     )

    valuation_account_id = fields.Many2one(
        'account.account', 
        string="Cuenta Contable de Valorización",
        related='categ_id.property_stock_valuation_account_id', 
        store=True,
        readonly=True
    )
    last_move_date = fields.Datetime(
        string='Fecha Último Movimiento',
        compute='_compute_last_move_date', store=False
    )

    move_type = fields.Selection(
        [('purchase', 'Compra'), ('internal', 'Transferencia Interna')],
        string='Tipo Movimiento',
        compute='_compute_last_move_info', store=False
    )

    valuation_value = fields.Float(
        string='Valorizado',
        compute='_compute_valuation_value', store=False
    )

    unit_value = fields.Float(
        string='Precio Promedio Unitario',
        compute='_compute_unit_value',
        store=False
    )

    total_valuation = fields.Float(
        string='Valor Total Valorizado',
        compute='_compute_total_valuation',
        store=False
    )

    def _compute_total_valuation(self):
        for product in self:
            # Obtener todos los quants del producto que tienen cantidad disponible
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id), ('quantity', '>', 0)])
            # Calcular el valor total valorizado
            product.total_valuation = sum(quant.quantity * quant.product_id.standard_price for quant in quant_records)

    def _compute_unit_value(self):
        for product in self:
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id), ('quantity', '>', 0)])
            total_quantity = sum(quant.quantity for quant in quant_records)
            total_value = sum(quant.quantity * quant.product_id.standard_price for quant in quant_records)
            product.unit_val

    def _compute_location_ids(self):
         """Computa las ubicaciones donde está disponible el producto hasta la fecha consultada."""
         to_date = self.env.context.get('to_date')  # Fecha límite para consultar disponibilidad
         for product in self:
             domain = [('product_id', '=', product.id), ('quantity', '>', 0)]
             if to_date:
                 domain.append(('in_date', '<=', to_date))  # Considerar solo movimientos hasta la fecha
             quants = self.env['stock.quant'].search(domain)
             product.location_ids = quants.mapped('location_id')

    def _compute_lot_ids(self):
        """Computa los lotes disponibles para el producto hasta la fecha consultada."""
        to_date = self.env.context.get('to_date')  # Fecha límite para consultar disponibilidad
        for product in self:
            # Filtrar quants por producto y fecha
            domain = [('product_id', '=', product.id), ('quantity', '>', 0)]
            if to_date:
                domain.append(('in_date', '<=', to_date))  # Considerar solo movimientos hasta la fecha
            quants = self.env['stock.quant'].search(domain)

            # Obtener lotes válidos y asegurarse de que existan
            lot_ids = quants.mapped('lot_id').filtered(lambda lot: lot.exists())  # Filtra lotes válidos
            if lot_ids:
                product.lot_ids = [(6, 0, lot_ids.ids)]  # Asignar correctamente valores a un campo Many2many
            else:
                product.lot_ids = [(5,)]  # Limpia el campo si no hay lotes válidos

    def _compute_last_move_info(self):
        for product in self:
            last_move = self.env['stock.move'].search(
                [('product_id', '=', product.id)],
                order='date desc',
                limit=1
            )
            if last_move:
                product.last_move_date = last_move.date
                product.move_type = 'purchase' if last_move.picking_type_id.code == 'incoming' else 'internal'
            else:
                product.last_move_date = False
                product.move_type = False

    def _compute_valuation_value(self):
        for product in self:
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id)])
            quantity = sum(quant_records.mapped('quantity'))
            product.valuation_value = quantity * product.standard_price

    def _compute_last_move_date(self):
        """
        Calcula la fecha del último movimiento relacionado con el producto hasta la fecha de consulta.
        """
        to_date = self.env.context.get('to_date')  # Fecha límite para la consulta
        for product in self:
            domain = [
                ('product_id', '=', product.id),
                ('state', '=', 'done')
            ]
            if to_date:
                domain.append(('date', '<=', to_date))  # Considerar solo movimientos hasta la fecha

            # Buscar el movimiento más reciente hasta la fecha de consulta
            last_move = self.env['stock.move'].search(
                domain,
                order='date desc',
                limit=1
            )
            product.last_move_date = last_move.date if last_move else False


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    valuation_value = fields.Float(
        string='Valorizado',
        compute='_compute_valuation_value',
        store=False
    )

    weighted_average_price = fields.Float(
        string='Precio Promedio Ponderado',
        compute='_compute_weighted_average_price',
        store=False
    )

    unit_value = fields.Float(
        string='Precio Promedio Unitario',
        compute='_compute_unit_value', store=False
    )

    total_valuation = fields.Float(
        string='Valor Total Valorizado',
        compute='_compute_total_valuation', store=False
    )

    valuation_account_id = fields.Many2one(
        'account.account',
        string='Cuenta Contable',
        compute='_compute_valuation_account', store=False
    )

    move_type = fields.Selection(
        [('purchase', 'Compra'), ('internal', 'Transferencia Interna')],
        string='Tipo Movimiento',
        compute='_compute_move_info', store=False
    )

    last_move_date = fields.Datetime(
        string='Último Movimiento',
        compute='_compute_last_move_date', store=False
    )

    account_move_id = fields.Many2one(
        'account.move', string='Asiento Contable', readonly=True
    )

    @api.depends('product_id', 'location_id')
    def _compute_account_move(self):
        for quant in self:
            valuation_layer = self.env['stock.valuation.layer'].search([
                ('product_id', '=', quant.product_id.id),
                ('location_id', '=', quant.location_id.id),
            ], limit=1)
            quant.account_move_id = valuation_layer.account_move_id if valuation_layer else False


    def _compute_valuation_value(self):
        """
        Calcula el valor total valorizado para cada `stock.quant`.
        """
        for quant in self:
            price_unit = quant.weighted_average_price or quant.product_id.standard_price
            quant.valuation_value = max(quant.quantity, 0) * price_unit

    def _compute_weighted_average_price(self):
        """
        Calcula el precio promedio ponderado para cada `stock.quant`.
        """
        for quant in self:
            product = quant.product_id
            total_value = 0.0
            total_quantity = 0.0

            # Filtrar movimientos relevantes
            domain = [('product_id', '=', product.id), ('state', '=', 'done')]
            to_date = self.env.context.get('to_date')
            if to_date:
                domain.append(('date', '<=', to_date))

            moves = self.env['stock.move'].search(domain)
            for move in moves:
                if move.picking_type_id.code in ['incoming', 'inventory']:
                    total_value += move.price_unit * move.product_qty
                    total_quantity += move.product_qty
                elif move.picking_type_id.code == 'outgoing':
                    total_quantity -= move.product_qty

            quant.weighted_average_price = total_value / total_quantity if total_quantity > 0 else product.standard_price

    @api.depends('product_id')
    def _compute_unit_value(self):
        for quant in self:
            quant.unit_value = quant.product_id.standard_price

    @api.depends('quantity', 'unit_value')
    def _compute_total_valuation(self):
        for quant in self:
            quant.total_valuation = quant.quantity * quant.unit_value

    @api.depends('product_id')
    def _compute_valuation_account(self):
        for quant in self:
            quant.valuation_account_id = quant.product_id.categ_id.property_stock_valuation_account_id

    @api.depends('product_id')
    def _compute_move_info(self):
        for quant in self:
            last_move = self.env['stock.move'].search(
                [('product_id', '=', quant.product_id.id)],
                order='date desc',
                limit=1
            )
            if last_move:
                quant.move_type = 'purchase' if last_move.picking_type_id.code == 'incoming' else 'internal'
            else:
                quant.move_type = False

    @api.depends('product_id')
    def _compute_last_move_date(self):
        for quant in self:
            last_move = self.env['stock.move'].search(
                [('product_id', '=', quant.product_id.id)],
                order='date desc',
                limit=1
            )
            quant.last_move_date = last_move.date if last_move else False


class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

    unit_value = fields.Float(
        string='Precio Promedio Unitario',
        compute='_compute_unit_value', store=False
    )

    total_valuation = fields.Float(
        string='Valor Total Valorizado',
        compute='_compute_total_valuation', store=False
    )

    valuation_account_id = fields.Many2one(
        'account.account',
        string='Cuenta Contable',
        compute='_compute_valuation_account', store=False
    )

    move_type = fields.Selection(
        [('purchase', 'Compra'), ('internal', 'Transferencia Interna')],
        string='Tipo Movimiento',
        compute='_compute_move_type', store=False
    )

    last_move_date = fields.Datetime(
        string='Último Movimiento',
        compute='_compute_last_move_date', store=False
    )

    location_id = fields.Many2one(
        'stock.location',
        string='Ubicación',
        compute='_compute_location_id',
        store=True,
    )

    @api.depends('product_id', 'create_date')
    def _compute_location_id(self):
        """
        Determina la ubicación relevante del producto basada en los movimientos y cantidades disponibles.
        """
        for record in self:
            if record.product_id and record.create_date:
                # Buscar el último movimiento relevante para el producto antes de la fecha del registro
                moves = self.env['stock.move'].search([
                    ('product_id', '=', record.product_id.id),
                    ('state', '=', 'done'),
                    ('date', '<=', record.create_date),
                ], order='date desc', limit=1)

                if moves:
                    # Tomar la ubicación de destino del último movimiento
                    record.location_id = moves.location_dest_id
                else:
                    # Si no hay movimientos, buscar en stock.quant
                    quants = self.env['stock.quant'].search([
                        ('product_id', '=', record.product_id.id),
                        ('quantity', '>', 0),
                        ('in_date', '<=', record.create_date),
                        ('location_id.usage', 'in', ['internal', 'transit']),
                    ])
                    if quants:
                        # Seleccionar la ubicación con mayor cantidad disponible
                        location_quantities = {}
                        for quant in quants:
                            location = quant.location_id
                            location_quantities[location] = location_quantities.get(location, 0) + quant.quantity

                        best_location = max(location_quantities.items(), key=lambda x: x[1])[0]
                        record.location_id = best_location
                    else:
                        record.location_id = False
            else:
                record.location_id = False


    @api.depends('product_id')
    def _compute_unit_value(self):
        """
        Calcula el precio promedio unitario para el producto.
        """
        for layer in self:
            layer.unit_value = layer.product_id.standard_price

    @api.depends('quantity', 'unit_value')
    def _compute_total_valuation(self):
        """
        Calcula el valor total valorizado para el producto en el `valuation.layer`.
        """
        for layer in self:
            layer.total_valuation = layer.quantity * layer.unit_value

    @api.depends('product_id')
    def _compute_valuation_account(self):
        """
        Obtiene la cuenta contable asociada a la categoría del producto.
        """
        for layer in self:
            layer.valuation_account_id = layer.product_id.categ_id.property_stock_valuation_account_id

    @api.depends('product_id')
    def _compute_move_type(self):
        """
        Determina el tipo de movimiento asociado al producto.
        """
        for layer in self:
            last_move = self.env['stock.move'].search(
                [('product_id', '=', layer.product_id.id)],
                order='date desc',
                limit=1
            )
            if last_move:
                layer.move_type = 'purchase' if last_move.picking_type_id.code == 'incoming' else 'internal'
            else:
                layer.move_type = False

    @api.depends('product_id')
    def _compute_last_move_date(self):
        """
        Obtiene la fecha del último movimiento del producto.
        """
        for layer in self:
            last_move = self.env['stock.move'].search(
                [('product_id', '=', layer.product_id.id)],
                order='date desc',
                limit=1
            )
            layer.last_move_date = last_move.date if last_move else False


_logger = logging.getLogger(__name__)

class InventoryValuationReport(models.Model):
    _name = 'inventory.valuation.report'
    _description = 'Reporte de Valorización de Inventario con Ubicaciones'

    valuation_date = fields.Date(string='Fecha de Valorización', readonly=True)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    location_id = fields.Many2one('stock.location', string='Ubicación', readonly=True)
    lot_id = fields.Many2one('stock.lot', string='Lote', readonly=True)
    quantity = fields.Float(string='Cantidad Disponible', readonly=True)
    reserved_quantity = fields.Float(string='Cantidad Reservada', readonly=True)
    unit_value = fields.Float(string='Precio Promedio Unitario', store=True, readonly=True)
    total_valuation = fields.Float(string='Valor Total Valorizado',  store=True, readonly=True)
    layer_account_move_id = fields.Many2one('account.move', string='Asiento Contable (Valorización)', readonly=True)
    quant_account_move_id = fields.Many2one('account.move', string='Asiento Contable (Quant)', readonly=True)
    stock_move_date = fields.Datetime(string='Fecha del Movimiento', readonly=True)
    move_reference = fields.Char(string='Referencia del Movimiento', readonly=True)
    account_move_id = fields.Many2one('account.move', string='Asiento Contable General')
    valuation_account_id = fields.Many2one(
        'account.account',
        string='Cuenta Contable de Valorización',
        readonly=True,
        compute='_compute_valuation_account',
        store=True
    )

    @api.depends('product_id')
    def _compute_valuation_account(self):
        for record in self:
            record.valuation_account_id = record.product_id.categ_id.property_stock_valuation_account_id
   
    @api.depends('product_id')
    def _compute_unit_value(self):
        """
        Cálculo del valor unitario basado directamente en el costo estándar del producto.
        Fuerza la obtención del precio desde `product.product` o `product.template`.
        """
        for record in self:
            if record.product_id:
                # Forzar la obtención del costo estándar desde el modelo del producto
                product = self.env['product.product'].browse(record.product_id.id)
                record.unit_value = product.standard_price or 0.0
            else:
                # Si no hay producto, generar una advertencia en los logs
                _logger.warning("El registro %s no tiene un producto asociado.", record.id)
                record.unit_value = 0.0


    @api.depends('unit_value', 'quantity')
    def _compute_total_valuation(self):
        """
        Cálculo del valor total como cantidad disponible * valor unitario.
        """
        for record in self:
            # Validar que haya un valor unitario y cantidad válida antes de calcular
            if record.unit_value > 0 and record.quantity > 0:
                record.total_valuation = record.unit_value * record.quantity
            else:
                # Registrar advertencia en los logs si no se puede calcular
                if not record.unit_value:
                    _logger.warning(
                        "No se pudo calcular la valoración total para el producto %s debido a un valor unitario faltante.",
                        record.product_id.display_name if record.product_id else "Desconocido"
                    )
                if not record.quantity:
                    _logger.warning(
                        "No se pudo calcular la valoración total para el producto %s debido a una cantidad faltante.",
                        record.product_id.display_name if record.product_id else "Desconocido"
                    )
                record.total_valuation = 0.0




    def generate_data_by_orm(self, report_date):
        """
        Genera datos del informe utilizando el ORM, procesando en lotes para mayor eficiencia.
        Incluye información de cuentas contables, últimos movimientos y valores relacionados.
        """
        # Eliminar registros previos para evitar duplicados
        self.search([]).unlink()

        # Configuración para dividir la generación en lotes
        batch_size = 500
        products = self.env['product.product'].search([])  # Obtener todos los productos
        total_products = len(products)
        batches = range(0, total_products, batch_size)

        # Nombres completos de las sububicaciones a excluir
        excluded_location_names = [
            "MALO/STOCK/MALO CD",
            "MALO/STOCK/MALO CORONEL",
            "MALO/STOCK/MALO LINARES",
            "MALO/STOCK/MALO PAINE",
            "MALO/STOCK/MALO TALCA",
            "Physical Locations/Traslado entre almacenes"
        ]

        for offset in batches:
            # Obtener un lote de productos
            product_batch = products[offset:offset + batch_size]
            
            # Preparar registros para insertar
            records_to_create = []
            for product in product_batch:
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('quantity', '>', 0),
                    ('location_id.usage', 'in', ['internal', 'transit'])  # Filtrar ubicaciones válidas
                ])
                for quant in quants:
                    # Validar si la ubicación debe ser excluida
                    if quant.location_id.complete_name in excluded_location_names:
                        continue  # Saltar este registro
                    
                    # Buscar información relacionada
                    valuation_layer = self.env['stock.valuation.layer'].search([
                        ('product_id', '=', quant.product_id.id),
                        ('create_date', '<=', report_date)
                    ], limit=1, order='create_date desc')

                    last_move = self.env['stock.move'].search([
                        ('product_id', '=', quant.product_id.id),
                        ('state', '=', 'done'),
                        ('date', '<=', report_date)
                    ], limit=1, order='date desc')

                    # Calcular el precio unitario
                    unit_value = product.standard_price  # Usar costo estándar por defecto
                    if valuation_layer and valuation_layer.unit_cost:
                        unit_value = valuation_layer.unit_cost

                    # Asegurar que el unit_value no sea nulo o inválido
                    unit_value = unit_value or 0.0

                    # Crear un diccionario con los datos del registro
                    records_to_create.append({
                        'valuation_date': report_date,
                        'product_id': quant.product_id.id,
                        'location_id': quant.location_id.id,
                        'lot_id': quant.lot_id.id if quant.lot_id else None,
                        'quantity': quant.quantity,
                        'reserved_quantity': quant.reserved_quantity,
                        'unit_value': unit_value,
                        'total_valuation': unit_value * quant.quantity,  # Calcular el total
                        'layer_account_move_id': valuation_layer.account_move_id.id if valuation_layer else None,
                        'stock_move_date': last_move.date if last_move else None,
                        'move_reference': last_move.reference if last_move else None,
                        'account_move_id': last_move.account_move_ids[:1].id if last_move else None,
                        'create_uid': self.env.uid,
                        'create_date': fields.Datetime.now(),
                        'write_uid': self.env.uid,
                        'write_date': fields.Datetime.now(),
                    })

            # Validar registros a insertar para excluir ubicaciones
            records_to_create = [
                record for record in records_to_create 
                if self.env['stock.location'].browse(record['location_id']).complete_name not in excluded_location_names
            ]

            # Insertar los registros en lotes
            if records_to_create:
                self.create(records_to_create)

            # Progresar en el log para grandes volúmenes de datos
            _logger.info("Processed batch %s/%s", offset + batch_size, total_products)




    def generate_data_by_account_moves(self, report_date):
        """
        Genera el reporte basado en los asientos contables validados.
        Incluye cálculos para movimientos positivos y negativos.
        """
        # Eliminar registros previos para evitar duplicados
        self.search([]).unlink()

        # Obtener las cuentas contables de valorización del inventario
        inventory_accounts = self.env['account.account'].search([
            ('id', 'in', self.env['product.category'].search([]).mapped('property_stock_valuation_account_id.id'))
        ])

        # Configuración para procesar en lotes
        batch_size = 500
        move_lines = self.env['account.move.line'].search([
            ('account_id', 'in', inventory_accounts.ids),  # Solo cuentas de inventario
            ('move_id.state', '=', 'posted'),             # Solo asientos contables validados
            ('date', '<=', report_date),                  # Movimientos hasta la fecha del reporte
        ])

        total_lines = len(move_lines)
        batches = range(0, total_lines, batch_size)

        for offset in batches:
            # Obtener un lote de líneas contables
            move_line_batch = move_lines[offset:offset + batch_size]

            # Preparar registros para insertar
            records_to_create = []
            for line in move_line_batch:
                product = line.product_id
                if not product:
                    continue  # Ignorar líneas sin producto

                # Determinar la ubicación desde la línea contable (si aplica)
                location = line.move_id.picking_id.location_dest_id if line.debit > 0 else line.move_id.picking_id.location_id

                # Excluir ubicaciones no deseadas
                if location and location.usage in ['production', 'inventory']:
                    continue

                # Determinar cantidad y valor
                quantity = line.quantity or 0.0
                unit_value = product.standard_price
                total_valuation = unit_value * quantity

                # Registrar el movimiento
                records_to_create.append({
                    'valuation_date': line.date,
                    'product_id': product.id,
                    'location_id': location.id if location else None,
                    'lot_id': line.lot_id.id if line.lot_id else None,
                    'quantity': quantity if line.debit > 0 else -quantity,
                    'unit_value': unit_value,
                    'total_valuation': total_valuation if line.debit > 0 else -total_valuation,
                    'account_move_id': line.move_id.id,
                    'create_uid': self.env.uid,
                    'create_date': fields.Datetime.now(),
                    'write_uid': self.env.uid,
                    'write_date': fields.Datetime.now(),
                })

            # Insertar registros en lotes
            if records_to_create:
                self.create(records_to_create)

            # Progresar en el log para grandes volúmenes de datos
            _logger.info("Processed batch %s/%s", offset + batch_size, total_lines)









    # def generate_data_by_orm(self, report_date):
    #     """
    #     Genera datos del informe utilizando el ORM, procesando en lotes para mayor eficiencia.
    #     Incluye información de cuentas contables, últimos movimientos y valores relacionados.
    #     """
    #     # Eliminar registros previos para evitar duplicados
    #     self.search([]).unlink()

    #     # Configuración para dividir la generación en lotes
    #     batch_size = 500
    #     products = self.env['product.product'].search([])  # Obtener todos los productos
    #     total_products = len(products)
    #     batches = range(0, total_products, batch_size)

    #     for offset in batches:
    #         # Obtener un lote de productos
    #         product_batch = products[offset:offset + batch_size]
            
    #         # Preparar registros para insertar
    #         records_to_create = []
    #         for product in product_batch:
    #             quants = self.env['stock.quant'].search([
    #                 ('product_id', '=', product.id),
    #                 ('quantity', '>', 0),
    #                 ('location_id.usage', 'in', ['internal', 'transit'])  # Filtrar ubicaciones
    #             ])
    #             for quant in quants:
    #                 # Buscar información relacionada
    #                 valuation_layer = self.env['stock.valuation.layer'].search([
    #                     ('product_id', '=', quant.product_id.id),
    #                     ('create_date', '<=', report_date)
    #                 ], limit=1, order='create_date desc')

    #                 last_move = self.env['stock.move'].search([
    #                     ('product_id', '=', quant.product_id.id),
    #                     ('state', '=', 'done'),
    #                     ('date', '<=', report_date)
    #                 ], limit=1, order='date desc')

    #                 # Calcular el precio unitario
    #                 unit_value = valuation_layer.unit_cost if valuation_layer and valuation_layer.unit_cost else product.standard_price 

    #                 # Log para verificar los valores obtenidos
    #                 _logger.info("Processed Product: %s, Unit Value: %s", product.display_name, unit_value)

    #                 # Crear un diccionario con los datos del registro
    #                 records_to_create.append({
    #                     'valuation_date': report_date,
    #                     'product_id': quant.product_id.id,
    #                     'location_id': quant.location_id.id,
    #                     'lot_id': quant.lot_id.id if quant.lot_id else None,
    #                     'quantity': quant.quantity,
    #                     'reserved_quantity': quant.reserved_quantity,
    #                     'unit_value': unit_value,
    #                     'total_valuation': unit_value * quant.quantity,  # Calcular el total
    #                     'layer_account_move_id': valuation_layer.account_move_id.id if valuation_layer else None,
    #                     'stock_move_date': last_move.date if last_move else None,
    #                     'move_reference': last_move.reference if last_move else None,
    #                     'account_move_id': last_move.account_move_ids[:1].id if last_move else None,
    #                     'create_uid': self.env.uid,
    #                     'create_date': fields.Datetime.now(),
    #                     'write_uid': self.env.uid,
    #                     'write_date': fields.Datetime.now(),
    #                 })

    #         # Insertar los registros en lotes
    #         if records_to_create:
    #             self.create(records_to_create)

    #         # Progresar en el log para grandes volúmenes de datos
    #         _logger.info("Processed batch %s/%s", offset + batch_size, total_products)







class InventoryValuationWizard(models.TransientModel):
    _name = 'inventory.valuation.wizard'
    _description = 'Wizard para Generar Reporte de Valorización'

    report_date = fields.Date(string='Fecha del Reporte', required=True, default=fields.Date.context_today)

    def generate_report(self):
        """
        Genera el reporte basado en la fecha seleccionada.
        """
        if not self.report_date:
            raise UserError("Por favor, selecciona una fecha para generar el reporte.")
        self.env['inventory.valuation.report'].generate_data(self.report_date)

        # Devolver la vista del informe generado
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reporte de Valorización de Inventario',
            'res_model': 'inventory.valuation.report',
            'view_mode': 'tree,form',
            'context': {'default_report_date': self.report_date},
        }
    
    def generate_report_by_orm(self):
        """
        Genera el reporte basado en la fecha seleccionada.
        """
        if not self.report_date:
            raise UserError("Por favor, selecciona una fecha para generar el reporte.")
        self.env['inventory.valuation.report'].generate_data_by_orm(self.report_date)

        # Devolver la vista del informe generado
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reporte de Valorización de Inventario',
            'res_model': 'inventory.valuation.report',
            'view_mode': 'tree,form',
            'context': {'default_report_date': self.report_date},
        }

