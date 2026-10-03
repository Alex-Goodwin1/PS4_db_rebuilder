# fix_db — put the missing games back into the PS4 library

`fix_db` downloads `/system_data/priv/mms/app.db` from a jailbroken PS4 over the GoldHEN FTP server
and writes the rows of the games that are on the drives but do not show up in the library — after
moving an external HDD to another console, restoring app.db from a backup or a firmware update.
Firmware 5.05 – 13.02, both the 52- and the 57-column layout of `tbl_appbrowse_*`. Python is not
needed on the PC: `fix_db.exe` is prebuilt.

## Quick start

1. Unpack the archive into one folder — the `exe` and the `.bat` files must stay together.
2. Start GoldHEN on the PS4 with its FTP server (port 2121, login `username` / `password`).
3. Double click a launcher and type the IP of the console (Settings → Network → View connection
   status):

```
run_check.bat   check only: list the games that are missing in app.db (nothing is written)
run_apply.bat   write the fixed app.db back to the console
```

**After `--apply` log the PS4 user out or reboot the console**, otherwise PS4 keeps the old app.db
in memory. The original is kept in `tmp\app.db.orig` and `tmp\backup\app.db.<timestamp>`.

## Command line

```
fix_db.exe 192.0.2.10                          # check only
fix_db.exe 192.0.2.10 --apply                  # write app.db back to the console
fix_db.exe 192.0.2.10 --storage ext            # external HDD (ext0) only: --storage internal
fix_db.exe 192.0.2.10 --repair --apply         # rewrite hddLocation/metaDataPath of existing rows
fix_db.exe 192.0.2.10 --prune --apply          # + delete the rows of games that are gone
fix_db.exe 192.0.2.10 --titles CUSA00001,CUSA00002 --apply
fix_db.exe --offline --db tmp/app.db           # work on a local copy, no FTP at all
fix_db.exe --restore tmp/app.db.orig --apply   # put app.db back from a backup
```

`--yes` skips the confirmation question, `--db FILE` takes a local file instead of the console,
`--no-appinfo` leaves `tbl_appinfo` alone, `--no-backup` switches the timestamped backup off. If
the console is unreachable the tool prints one line (`cannot connect to PS4 at …`) and exits with
code 1 instead of a traceback.

## What it does

* looks for `XXXX00000` folders in `/mnt/ext0/user/app` and `/user/app`; a title id that is on both
  drives counts as external, exactly like the console does;
* reads `param.sfo` from `/system_data/priv/appmeta[/external]/<ID>` (cached in `tmp\appmeta\`);
* adds one row to **every** `tbl_appbrowse_*` table (the column list comes from the database
  itself) and a pseudo `app.info` to `tbl_appinfo`;
* verifies the result (`PRAGMA integrity_check`, `hddLocation` of every row, md5 after the upload)
  before the file goes to the console. Values the console writes itself (`pathInfo`, dates,
  `lastAccessIndex`) are not invented; only `contentSize` is approximate.

`--prune` deletes a row only when its `metaDataPath` points to a storage that was read successfully
and the game folder is gone. `NPXS*` rows, rows with `onDisc=1` and rows of an unreadable storage
are never touched; if no storage could be read at all, `--prune` does nothing.

## Files

```
fix_db.exe      the prebuilt program (no Python needed)
run_check.bat   check only, nothing is written to the console
run_apply.bat   write app.db back to the console
fix_db.py       the source: FTP, param.sfo, tbl_appbrowse_*, row writing
appinfo.py      a pseudo app.info for tbl_appinfo
sfo\            param.sfo reader (MIT, Copyright (c) 2016 cologler)
build_exe.bat   rebuild fix_db.exe (PyInstaller)
make_dist.bat   build dist\fix_db.zip and refresh SHA256SUMS.txt
SHA256SUMS.txt  hash of fix_db.exe
LICENSE         MIT
tmp\            created on the first run, never committed
```

## Build

```
python -m pip install pyinstaller
build_exe.bat                                  # rebuild fix_db.exe
python fix_db.py 192.0.2.10 --db tmp\app.db    # run from the sources
make_dist.bat                                  # dist\fix_db.zip + SHA256SUMS.txt
```

The exe is built with PyInstaller and is not code signed, so SmartScreen may show "Windows
protected your PC": choose More info → Run anyway. Compare the hash with `SHA256SUMS.txt`
(`certutil -hashfile fix_db.exe SHA256`). The second tool of the project lives in the
**PS4_hide_icons** repository and ships the same `fix_db.exe` as a helper: after a rebuild copy the
new exe there too.

## License

MIT, Copyright (c) 2026 Alex Goodwin — see `LICENSE`. Editing `app.db` means touching a system file,
everything is at your own risk.

---

# fix_db — русская версия

`fix_db` скачивает `/system_data/priv/mms/app.db` с консоли PS4 через FTP-сервер GoldHEN и
дописывает строки игр, которые лежат на дисках, но в библиотеке не показываются — после переноса
внешнего HDD на другую консоль, восстановления app.db из бэкапа или обновления прошивки.
Прошивки 5.05 – 13.02, оба layout'а `tbl_appbrowse_*` (52 и 57 колонок). Python на компьютере не
нужен: `fix_db.exe` уже собран.

## Быстрый старт

1. Распакуйте архив в одну папку — `exe` и `.bat` должны лежать рядом.
2. Запустите на PS4 GoldHEN с FTP-сервером (порт 2121, логин `username` / `password`).
3. Двойной щелчок по лаунчеру и введите IP консоли («Настройки → Сеть → Просмотр состояния
   соединения»):

```
run_check.bat   только проверка: список игр, которых нет в app.db (ничего не пишется)
run_apply.bat   записать исправленную app.db на консоль
```

**После `--apply` выйдите из пользователя PS4 или перезагрузите консоль** — иначе система
оставит в памяти старую копию app.db. Оригинал хранится в `tmp\app.db.orig` и
`tmp\backup\app.db.<дата-время>`.

## Командная строка

```
fix_db.exe 192.0.2.10                          # только проверка
fix_db.exe 192.0.2.10 --apply                  # записать app.db на консоль
fix_db.exe 192.0.2.10 --storage ext            # только внешний HDD (ext0); --storage internal
fix_db.exe 192.0.2.10 --repair --apply         # переписать hddLocation/metaDataPath у строк
fix_db.exe 192.0.2.10 --prune --apply          # + удалить строки игр, которых больше нет
fix_db.exe 192.0.2.10 --titles CUSA00001,CUSA00002 --apply
fix_db.exe --offline --db tmp/app.db           # работать с локальной копией, без FTP
fix_db.exe --restore tmp/app.db.orig --apply   # вернуть app.db из бэкапа
```

`--yes` — не спрашивать подтверждение, `--db FILE` — взять локальный файл вместо консоли,
`--no-appinfo` — не трогать `tbl_appinfo`, `--no-backup` — не делать копию с датой. Если консоль
недоступна, вместо трассировки печатается одна строка (`cannot connect to PS4 at …`) и код
возврата 1.

## Что делается

* ищет папки `XXXX00000` в `/mnt/ext0/user/app` и `/user/app`; один и тот же title id на двух
  дисках считается внешним — как и делает сама консоль;
* читает `param.sfo` из `/system_data/priv/appmeta[/external]/<ID>` (кэш в `tmp\appmeta\`);
* добавляет строку в **каждую** таблицу `tbl_appbrowse_*` (список колонок берётся из самой базы)
  и псевдо-`app.info` в `tbl_appinfo`;
* проверяет результат (`PRAGMA integrity_check`, `hddLocation` каждой строки, md5 после загрузки)
  и только затем отправляет файл на консоль. Значения, которые пишет сама система (`pathInfo`,
  даты, `lastAccessIndex`), не выдумываются; приблизительный только `contentSize`.

`--prune` удаляет строку, только если её `metaDataPath` указывает на успешно прочитанное
хранилище, а папки игры там уже нет. Строки `NPXS*`, строки с `onDisc=1` и строки нечитаемого
хранилища не трогаются; если не удалось прочитать ни одно хранилище, `--prune` ничего не делает.

## Файлы

```
fix_db.exe      готовая сборка (Python не нужен)
run_check.bat   только проверка, на консоль ничего не пишется
run_apply.bat   запись app.db на консоль
fix_db.py       исходник: FTP, param.sfo, tbl_appbrowse_*, запись строк
appinfo.py      псевдо-app.info для tbl_appinfo
sfo\            разбор param.sfo (MIT, Copyright (c) 2016 cologler)
build_exe.bat   пересобрать fix_db.exe (PyInstaller)
make_dist.bat   собрать dist\fix_db.zip и обновить SHA256SUMS.txt
SHA256SUMS.txt  хэш fix_db.exe
LICENSE         MIT
tmp\            создаётся при первом запуске, в git не попадает
```

## Сборка

```
python -m pip install pyinstaller
build_exe.bat                                  # пересобрать fix_db.exe
python fix_db.py 192.0.2.10 --db tmp\app.db    # запуск без сборки
make_dist.bat                                  # dist\fix_db.zip + SHA256SUMS.txt
```

exe собран PyInstaller и не подписан, поэтому SmartScreen может показать «Windows защитила ваш
компьютер»: «Подробнее» → «Выполнить в любом случае». Сверьте хэш с `SHA256SUMS.txt`
(`certutil -hashfile fix_db.exe SHA256`). Второй инструмент проекта лежит в репозитории
**PS4_hide_icons**, там та же сборка `fix_db.exe` используется как вспомогательная: после
пересборки положите новый exe и туда.

## Лицензия

MIT, Copyright (c) 2026 Alex Goodwin — см. `LICENSE`. Правка `app.db` — вмешательство в системный
файл консоли, всё делается на ваш риск.
