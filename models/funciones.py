 # def generate_data(self, report_date):
    #     """
    #     Genera datos del informe utilizando SQL para optimizar el rendimiento.
    #     """
    #     # Limpiar datos anteriores
    #     self.env.cr.execute("DELETE FROM inventory_valuation_report")

    #     # Consulta SQL para obtener datos de quants y valuation layers
    #     query = """
    #         INSERT INTO inventory_valuation_report (
    #             valuation_date,
    #             product_id,
    #             location_id,
    #             lot_id,
    #             quantity,
    #             reserved_quantity,
    #             unit_value,
    #             total_valuation,
    #             layer_account_move_id,
    #             stock_move_date,
    #             move_reference,
    #             create_uid,
    #             create_date,
    #             write_uid,
    #             write_date
    #         )
    #         SELECT
    #             %s AS valuation_date,
    #             quant.product_id AS product_id,
    #             quant.location_id AS location_id,
    #             quant.lot_id AS lot_id,
    #             quant.quantity AS quantity,
    #             quant.reserved_quantity AS reserved_quantity,
    #             COALESCE(valuation.unit_cost, pt.standard_price) AS unit_value,
    #             COALESCE(quant.quantity * valuation.unit_cost, quant.quantity * pt.standard_price) AS total_valuation,
    #             valuation.account_move_id AS layer_account_move_id,
    #             move.date AS stock_move_date,
    #             move.reference AS move_reference,
    #             %s AS create_uid,
    #             NOW() AS create_date,
    #             %s AS write_uid,
    #             NOW() AS write_date
    #         FROM
    #             stock_quant AS quant
    #         LEFT JOIN
    #             stock_valuation_layer AS valuation
    #         ON
    #             quant.product_id = valuation.product_id
    #             AND quant.location_id = valuation.location_id
    #             AND valuation.create_date <= %s
    #         LEFT JOIN
    #             stock_move AS move
    #         ON
    #             move.product_id = quant.product_id
    #             AND move.state = 'done'
    #             AND move.date <= %s
    #         LEFT JOIN
    #             product_product AS pp
    #         ON
    #             quant.product_id = pp.id
    #         LEFT JOIN
    #             product_template AS pt
    #         ON
    #             pp.product_tmpl_id = pt.id
    #         WHERE
    #             quant.quantity > 0
    #     """
    #     # Ejecutar la consulta con parámetros
    #     params = [
    #         report_date,
    #         self.env.uid,  # create_uid
    #         self.env.uid,  # write_uid
    #         report_date,   # valuation_date para valuation layers
    #         report_date    # stock_move.date
    #     ]
    #     self.env.cr.execute(query, params)

    # @api.model
    # def generate_data(self, report_date):
    #     """
    #     Genera los datos del reporte utilizando el ORM.
    #     """
    #     # Borrar datos previos
    #     self.env.cr.execute("DELETE FROM inventory_valuation_report")

    #     products = self.env['product.product'].search([('type', '=', 'product')])

    #     records_to_create = []
    #     for product in products:
    #         # Consultar stock.valuation.layer para el producto
    #         valuation_layers = self.env['stock.valuation.layer'].search([
    #             ('product_id', '=', product.id),
    #             ('create_date', '<=', report_date)
    #         ])
    #         # Consultar stock.quant para el producto
    #         quants = self.env['stock.quant'].search([
    #             ('product_id', '=', product.id),
    #             ('quantity', '>', 0),
    #             ('in_date', '<=', report_date)
    #         ])

    #         for quant in quants:
    #             # Obtener datos del lote, ubicación y cantidades
    #             lot_id = quant.lot_id.id if quant.lot_id else False
    #             location_id = quant.location_id.id
    #             quantity = quant.quantity
    #             reserved_quantity = quant.reserved_quantity

    #             # Calcular valorización y unit value
    #             unit_value = product.standard_price
    #             total_valuation = quantity * unit_value

    #             # Asociar movimiento contable si aplica
    #             relevant_layers = valuation_layers.filtered(lambda v: v.location_id == quant.location_id)
    #             layer_account_move_id = relevant_layers[0].account_move_id.id if relevant_layers else False  # Selecciona el primer registro

    #             # Obtener datos del movimiento de stock
    #             stock_move = self.env['stock.move'].search([
    #                 ('product_id', '=', product.id),
    #                 ('state', '=', 'done'),
    #                 ('date', '<=', report_date)
    #             ], limit=1, order='date desc')

    #             move_reference = stock_move.reference if stock_move else False
    #             stock_move_date = stock_move.date if stock_move else False

    #             # Crear el registro
    #             records_to_create.append({
    #                 'valuation_date': report_date,
    #                 'product_id': product.id,
    #                 'location_id': location_id,
    #                 'lot_id': lot_id,
    #                 'quantity': quantity,
    #                 'reserved_quantity': reserved_quantity,
    #                 'unit_value': unit_value,
    #                 'total_valuation': total_valuation,
    #                 'layer_account_move_id': layer_account_move_id,
    #                 'stock_move_date': stock_move_date,
    #                 'move_reference': move_reference,
    #             })

    #     # Crear los registros en batch
    #     self.create(records_to_create)


   #  def generate_data_by_orm(self, report_date):
   #      """
   #      Genera datos del informe utilizando el ORM de Odoo.
   #      Filtra productos con stock disponible relacionado con stock.quant, stock.move, stock.valuation.layer y account.move.
   #      """
   #      InventoryValuationReport = self.env['inventory.valuation.report']
   #      Product = self.env['product.product']

   #      # Limpiar datos anteriores
   #      InventoryValuationReport.sudo().search([]).unlink()

   #      # Filtrar productos con stock disponible
   #      quants = self.env['stock.quant'].search([
   #          ('quantity', '>', 0),
   #          ('location_id.usage', 'in', ['internal', 'transit'])  # Considerar solo ubicaciones internas y de tránsito
   #      ])

   #      product_ids = quants.mapped('product_id.id')
   #      location_ids = quants.mapped('location_id.id')
   #      lot_ids = quants.mapped('lot_id.id')

   #      # Obtener movimientos de stock relacionados
   #      moves = self.env['stock.move'].search([
   #          ('product_id', 'in', product_ids),
   #          ('state', '=', 'done'),
   #          ('date', '<=', report_date)
   #      ])

   #      move_map = {move.product_id.id: move for move in moves}

   #      # Obtener capas de valoración relacionadas
   #      valuation_layers = self.env['stock.valuation.layer'].search([
   #          ('product_id', 'in', product_ids),
   #          ('create_date', '<=', report_date)
   #      ])

   #      valuation_map = {vl.product_id.id: vl for vl in valuation_layers}

   #      # Obtener asientos contables relacionados
   #      account_moves = self.env['account.move'].search([
   #          ('id', 'in', valuation_layers.mapped('account_move_id.id')),
   #          ('state', '=', 'posted')
   #      ])

   #      account_move_map = {am.id: am for am in account_moves}

   #      # Generar datos del informe
   #      records = []
   #      for quant in quants:
   #          product_id = quant.product_id.id
   #          location_id = quant.location_id.id
   #          lot_id = quant.lot_id.id

   #          move = move_map.get(product_id)
   #          valuation_layer = valuation_map.get(product_id)
   #          account_move = account_move_map.get(valuation_layer.account_move_id.id) if valuation_layer else None

   #          if not (move and valuation_layer and account_move):
   #              continue

   #          records.append({
   #              'valuation_date': report_date,
   #              'product_id': product_id,
   #              'location_id': location_id,
   #              'lot_id': lot_id,
   #              'quantity': quant.quantity,
   #              'reserved_quantity': quant.reserved_quantity,
   #              'layer_account_move_id': valuation_layer.account_move_id.id if valuation_layer else False,
   #              'stock_move_date': move.date if move else False,
   #              'move_reference': move.reference if move else '',
   #              'create_uid': self.env.uid,
   #              'create_date': fields.Datetime.now(),
   #              'write_uid': self.env.uid,
   #              'write_date': fields.Datetime.now(),
   #          })

   #      # Insertar los registros en lotes de 500
   #      batch_size = 500
   #      for i in range(0, len(records), batch_size):
   #          InventoryValuationReport.sudo().create(records[i:i + batch_size])
