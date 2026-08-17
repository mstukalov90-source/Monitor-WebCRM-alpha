-- Display name for CRM users (Russian "Фамилия И. О."; login stays the identifier).

ALTER TABLE crm.users
    ADD COLUMN IF NOT EXISTS name TEXT;

UPDATE crm.users SET name = 'Администратор' WHERE login = 'admin';
UPDATE crm.users SET name = 'Борисов А. М.' WHERE login = 'BorisovAM';
UPDATE crm.users SET name = 'Борисов А. М.' WHERE login = 'BorisovAM1';
UPDATE crm.users SET name = 'Борисов А. С.' WHERE login = 'BorisovAS';
UPDATE crm.users SET name = 'Чернышев В. Г.' WHERE login = 'ChernishevVG';
UPDATE crm.users SET name = 'Чуйкин М. А.' WHERE login = 'ChuykinMA';
UPDATE crm.users SET name = 'Герасимчук А. М.' WHERE login = 'GerasimchukAM';
UPDATE crm.users SET name = 'Косолапов Р. С.' WHERE login = 'KosolapovRS';
UPDATE crm.users SET name = 'Лифанов А. С.' WHERE login = 'LifanovAS';
UPDATE crm.users SET name = 'Махаринец У. К.' WHERE login = 'MakharinetsUK';
UPDATE crm.users SET name = 'Михеев М. В.' WHERE login = 'MikheevMV';
UPDATE crm.users SET name = 'Мягкова А. А.' WHERE login = 'MyagkovaAA';
UPDATE crm.users SET name = 'Нефедова О. А.' WHERE login = 'NefedovaOA';
UPDATE crm.users SET name = 'Орехов Р. С.' WHERE login = 'OrekhovRS';
UPDATE crm.users SET name = 'Прусов Б. Б.' WHERE login = 'PrusovBB';
UPDATE crm.users SET name = 'Самсонов А. Е.' WHERE login = 'SamsonovAE';
UPDATE crm.users SET name = 'Сидоров А. Н.' WHERE login = 'SidorovAN';
UPDATE crm.users SET name = 'Синельщиков С. М.' WHERE login = 'SinelshchikovSM';
UPDATE crm.users SET name = 'Скачков Н. А.' WHERE login = 'SkachkovNA';
UPDATE crm.users SET name = 'Скроцкий И. А.' WHERE login = 'SkrotskiyIA';
UPDATE crm.users SET name = 'Слапик И. А.' WHERE login = 'SlapikIA';
UPDATE crm.users SET name = 'Струнникова О. А.' WHERE login = 'StrunnikovaOA';
UPDATE crm.users SET name = 'Стукалов М. Н.' WHERE login = 'StukalovMN';
UPDATE crm.users SET name = 'Тарлаков А. Р.' WHERE login = 'TarlakovAR';
UPDATE crm.users SET name = 'Ведяскин Н. А.' WHERE login = 'VedyaskinNA';
UPDATE crm.users SET name = 'Жученко А. А.' WHERE login = 'ZhuchenkoAA';
