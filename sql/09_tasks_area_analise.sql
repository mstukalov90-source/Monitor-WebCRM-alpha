-- Флаг анализа площадного заказа
ALTER TABLE crm.tasks_area ADD COLUMN IF NOT EXISTS analise BOOLEAN;
