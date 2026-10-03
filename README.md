# fix_db — регистрация игр в app.db (PS4, прошивка 11.00 – 13.02)

Скрипт добавляет в базу консоли (`/system_data/priv/mms/app.db`) строки игр, которые
лежат на дисках, но в библиотеке не показываются. Так бывает, когда внешний HDD
перенесли на другую консоль, восстанавливали app.db из бэкапа или обновили прошивку —
папки игр на месте, а записей о них в базе нет.

Поддерживаются **оба** накопителя:

| Хранилище | Где лежат игры | Что ставит `metaDataPath` |
|--|--|--|
| внешний HDD (ext0) | `/mnt/ext0/user/app/<TITLE_ID>` | `/user/appmeta/external/<TITLE_ID>` |
| внутренний HDD консоли | `/user/app/<TITLE_ID>` | `/user/appmeta/<TITLE_ID>` |

## Что нужно

* Windows. Готовая сборка `fix_db.exe` — Python на компьютере не нужен, рядом с ней
  создаётся только рабочая папка `tmp\`. Архив распаковывайте целиком: `fix_db.exe` и
  `run_*.bat` должны лежать в одной папке.
* На PS4 запущен GoldHEN с FTP-сервером (порт 2121, логин/пароль по умолчанию
  `username` / `password`).
* Консоль включена и находится в той же сети.

## Как пользоваться

Самый простой способ — двойной щелчок по `run_check.bat` (только проверка) или
`run_apply.bat` (запись app.db на консоль). Оба спрашивают IP консоли (адрес виден в
«Настройки → Сеть → Просмотр состояния соединения»); в примерах ниже вместо него
стоит условный `192.0.2.10`. Лаунчеры запускают `fix_db.exe` из этой же папки.

Вручную:

```
fix_db.exe 192.0.2.10                       # только проверка, на PS4 ничего не пишется
fix_db.exe 192.0.2.10 --apply               # записать исправленную app.db на PS4
fix_db.exe 192.0.2.10 --storage internal    # только игры внутреннего HDD
fix_db.exe 192.0.2.10 --storage ext         # только внешний HDD (ext0)
fix_db.exe 192.0.2.10 --repair --apply      # переписать hddLocation/metaDataPath
                                              # у строк, которые уже есть
fix_db.exe 192.0.2.10 --prune --apply       # + удалить строки игр, которых больше нет
fix_db.exe 192.0.2.10 --titles CUSA00001,CUSA00002 --apply
fix_db.exe --offline --db tmp/app.db           # пересобрать локальную копию, без FTP
fix_db.exe --restore tmp/app.db.orig --apply   # вернуть app.db из бэкапа
```

После `--apply`: **выйдите из пользователя PS4 или перезагрузите консоль** — только тогда
система перечитает app.db. Игры появятся в библиотеке, значки — на домашнем экране.

Если запускать `run_apply.bat` / скрипт с `--apply` без `--yes` в консоли Windows, скрипт
спросит подтверждение перед загрузкой. Ключ `--yes` — «не спрашивать».

Если IP неверный или консоль недоступна, вместо простыни трассировки печатается одна
строка и код возврата 1:

```
cannot connect to PS4 at 192.0.2.10:2121 -- [WinError 10061] соединение не установлено
  check that the IP is right and that GoldHEN runs its FTP server on this port
  (if the login was changed, pass --user/--password)
```

## Что именно правится

1. Скачивает app.db и складывает копию оригинала в `tmp\backup\app.db.ГГГГММДД-ЧЧММСС`
   (хронологию можно отключить ключом `--no-backup`).
2. Просматривает `/mnt/ext0/user/app` и/или `/user/app` и берёт только папки вида
   `XXXX00000`. Один и тот же title id на обоих накопителях считается как внешний —
   именно так делает сама консоль.
3. Для каждой найденной игры читает `param.sfo` из
   `/system_data/priv/appmeta[/external]/<ID>` (копия кэшируется в `tmp\appmeta\...`).
4. Добавляет по одной строке в **каждую** таблицу `tbl_appbrowse_*`. Список колонок
   скрипт берёт из самой базы, поэтому подходит и 52-колоночный layout 5.05/6.72, и
   57-колоночный 11.00 – 13.02.
5. Добавляет ключи в `tbl_appinfo` (кроме ключей, которые консоль не хранит:
   `DEV_FLAG`, `PUBTOOLINFO`, `PUBTOOLVER`, `PUBTOOLMINVER`).
6. Проверяет результат (`PRAGMA integrity_check`, `hddLocation` у каждой строки) и только
   после этого загружает базу обратно на PS4.

Значения, которые система пишет сама (`pathInfo`, `pathInfo2`, даты, `lastAccessIndex`
берётся как `tbl_version.access_index + 1`…), скрипт не выдумывает: `pathInfo` он никогда
не переписывает у существующих строк, а `lastAccessIndex` внутри новой строки монотонно
увеличивает.

## Удаление битых строк (`--prune`)

Когда игру удалили мимо консоли (или к приставке подключили чужой HDD), в
`tbl_appbrowse_*` остаётся строка, а папки игры на диске уже нет — плитка в библиотеке
висит пустой. Ключ `--prune` такие строки удаляет.

Битой считается строка, у которой `metaDataPath` указывает на **проверенный** накопитель,
а папки `/app/<TITLE_ID>` там нет. Скрипт при этом **никогда** не трогает:

* строки `NPXS*` — их пишет сама прошивка, папки на диске у системных приложений нет;
* строки с `onDisc=1` — игра запускалась с диска, места на HDD у неё может не быть;
* строки накопителя, который не удалось прочитать (нет доступа или FTP);
* строки без `metaDataPath` и таблицы без колонки `metaDataPath` или `onDisc`
  (неизвестный layout) — они только перечисляются в отчёте.

Вместе со строками `tbl_appbrowse_*` удаляются и строки `tbl_appinfo` этих игр
(отключается ключом `--no-appinfo`). Если не прочитался **ни один** накопитель (например,
внешний HDD не подключён), `--prune` не делает ничего: иначе все внешние игры были бы
приняты за битые. Без `--prune` найденные строки только перечисляются в отчёте:

```
broken rows: 2 title id(s), 4 row(s) - no game folder on external HDD:
  CUSA00102  Demo game, external          external HDD   2 row(s)
```

Перед записью скрипт проверяет, что удалённых title id не осталось ни в одной таблице
(`prune verification: ... integrity_check=ok`), а копия исходной базы лежит в `tmp\backup\`.

## Важные детали

* **Локальная копия.** Работа идёт над `tmp\app.db`; на консоль файл уходит только с
  `--apply` (плюс сверка md5 после загрузки). Оригинал всегда лежит в `tmp\app.db.orig`.
* **contentSize — единственное «неточное» поле.** Для игр на внешнем HDD берётся размер
  `app.pkg` (через MLSD/LIST: ответ `SIZE` у GoldHEN «переполняется» на файлах больше
  4 ГиБ). Для внутренних игр берётся оценка из `app.json` (сумма частей) — это размер
  *загрузки*, а app.db хранит размер *установленного* контента, который знает только сама
  консоль. На появление игры в библиотеке это не влияет; ключ
  `--no-appinfo` отключает работу с `tbl_appinfo` целиком.
* **`--repair`** исправляет только `hddLocation` и `metaDataPath` у строк, которые уже
  существуют (например, строки от внутренних игр, оставшиеся после переноса на внешний
  HDD). Остальные значения не трогаются.
* **`--offline` без FTP.** С ключом `--offline --db <файл>` скрипт работает только с
  локальной копией: `--apply` в этом режиме ничего не загружает (в отчёте будет
  `offline mode, nothing was uploaded`). Готовую базу можно залить позже командой
  `fix_db.exe PS4_IP --db tmp\app.db --apply --yes`.
* **Откат.** `fix_db.exe --restore tmp\backup\app.db.20260101-120000 --apply`
  (или `tmp\app.db.orig`) вернёт базу на место.

## Файлы

```
fix_db.exe      готовая сборка: run_check.bat/run_apply.bat запускают её с нужным ключом,
                Python на компьютере не требуется
run_check.bat   проверка без записи на консоль
run_apply.bat   запись app.db на консоль
README.md       этот файл
LICENSE         лицензия MIT
tmp\            создаётся при первом запуске: app.db, app.db.orig, backup\, appmeta\, отчёты

fix_db.py       исходник: FTP, param.sfo, layout таблиц tbl_appbrowse_*, запись строк
appinfo.py      псевдо-app.info для tbl_appinfo
sfo\            библиотека разбора param.sfo (MIT, Copyright (c) 2016 cologler)
build_exe.bat   пересобрать fix_db.exe (PyInstaller)
make_dist.bat   собрать архив релиза в dist\ и обновить SHA256SUMS.txt
make_dist.ps1   то, что вызывает make_dist.bat
SHA256SUMS.txt  хэш fix_db.exe
```

Репозиторий называется **PS4_db_rebuilder**. Второй инструмент проекта — отдельный
репозиторий **PS4_hide_icons** (значки домашнего экрана): там лежит та же сборка
`fix_db.exe` как вспомогательная программа, поэтому после пересборки положите новый
`fix_db.exe` в оба репозитория.

## Сборка exe из исходников

Нужен Python 3.8+ и PyInstaller:

```
python -m pip install pyinstaller
build_exe.bat
```

Скрипт собирает `fix_db.exe` рядом с исходниками (`pyinstaller --onefile --console --clean`),
служебная папка `build\` в git не попадает. Запуск без сборки:
`python fix_db.py 192.0.2.10 --db tmp\app.db`.

Архив для раздела Releases собирается отдельно:

```
make_dist.bat   -> dist\fix_db.zip, dist\SHA256SUMS.txt
```

## Проверка хэшей

```
certutil -hashfile fix_db.exe SHA256
```

Сверьте результат с `SHA256SUMS.txt`. exe собран PyInstaller и не подписан, поэтому
SmartScreen может показать «Windows защитила ваш компьютер»: «Подробнее» → «Выполнить
в любом случае».

---

## English

The script adds rows for games that are on the drives of the console but do not show up in the
library — after moving an external HDD to another console, restoring app.db from a backup or a
firmware update the game folders are there, but their rows are missing. Both storages are
supported:

| storage | where the games are | `metaDataPath` written by the script |
|--|--|--|
| external HDD (ext0) | `/mnt/ext0/user/app/<TITLE_ID>` | `/user/appmeta/external/<TITLE_ID>` |
| internal HDD of the console | `/user/app/<TITLE_ID>` | `/user/appmeta/<TITLE_ID>` |

### Requirements

* Windows. The prebuilt `fix_db.exe` needs no Python; only a `tmp\` folder is created next to it.
  Unpack the whole archive: `fix_db.exe` and the `run_*.bat` files must stay in one folder.
* GoldHEN with its FTP server on the PS4 (port 2121, default login `username` / `password`).
* The console is powered on and in the same network.

### Usage

Double click `run_check.bat` (check only) or `run_apply.bat` (write app.db to the console). Both
ask for the IP of the console (it is shown in Settings → Network → View Connection Status); the
examples below use `192.0.2.10`.

```
fix_db.exe 192.0.2.10                       # check only, nothing is written to the PS4
fix_db.exe 192.0.2.10 --apply               # write the fixed app.db to the PS4
fix_db.exe 192.0.2.10 --storage internal    # only games of the internal HDD
fix_db.exe 192.0.2.10 --storage ext         # only the external HDD (ext0)
fix_db.exe 192.0.2.10 --repair --apply      # rewrite hddLocation/metaDataPath of existing rows
fix_db.exe 192.0.2.10 --prune --apply       # + delete the rows of games that are gone
fix_db.exe 192.0.2.10 --titles CUSA00001,CUSA00002 --apply
fix_db.exe --offline --db tmp/app.db           # rebuild the local copy, no FTP
fix_db.exe --restore tmp/app.db.orig --apply   # put app.db back from a backup
```

After `--apply` **log the PS4 user out or reboot the console**: only then PS4 reads app.db again,
the games appear in the library and the icons on the home screen. Running the launcher or the
script with `--apply` without `--yes` asks for confirmation before uploading; `--yes` means
"do not ask".

If the IP is wrong or the console is unreachable, one line is printed instead of a traceback (the
exit code is 1):

```
cannot connect to PS4 at 192.0.2.10:2121 -- [WinError 10061] connection refused
  check that the IP is right and that GoldHEN runs its FTP server on this port
  (if the login was changed, pass --user/--password)
```

### What exactly is changed

1. app.db is downloaded and the original is copied to `tmp\backup\app.db.<timestamp>`
   (`--no-backup` switches that off).
2. `/mnt/ext0/user/app` and/or `/user/app` are scanned for folders named `XXXX00000`. A title id
   found on both storages counts as external — exactly like the console does it.
3. `param.sfo` is read from `/system_data/priv/appmeta[/external]/<ID>` (a copy is cached in
   `tmp\appmeta\...`).
4. One row is added to **every** table `tbl_appbrowse_*`. The column list is read from the
   database itself, so the 52-column layout of 5.05/6.72 and the 57-column layout of 11.00 – 13.02
   both work.
5. `tbl_appinfo` gets a pseudo `app.info` built from param.sfo.
6. The result is verified (`PRAGMA integrity_check`, `hddLocation` of every row) and only then
   uploaded back to the PS4 (`md5` of the uploaded file is compared).

Values the system writes itself (`pathInfo`, `pathInfo2`, dates, `lastAccessIndex` taken from
`tbl_version.access_index + 1`, ...) are not invented: `pathInfo` of existing rows is never
rewritten and `lastAccessIndex` of a new row increases monotonically.

### Deleting broken rows (`--prune`)

When a game was deleted outside of the console (or somebody else's HDD was attached), a row stays
in `tbl_appbrowse_*` while the game folder is gone — the tile in the library stays empty. `--prune`
deletes such rows.

A row counts as broken when its `metaDataPath` points to a **verified** storage and there is no
`/app/<TITLE_ID>` folder there. The script never touches:

* `NPXS*` rows — the firmware writes them and system apps have no folder on the disk;
* rows with `onDisc=1` — the game was launched from a disc and may have no files on the HDD;
* rows of a storage that could not be listed (no access or FTP);
* rows without `metaDataPath` and tables without a `metaDataPath` or `onDisc` column (unknown
  layout) — those are only listed in the report.

Together with the `tbl_appbrowse_*` rows the `tbl_appinfo` rows of those games are deleted
(`--no-appinfo` switches that off). If **no** storage could be read (for example the external HDD is
not connected), `--prune` does nothing: otherwise every external game would be taken for broken.
Without `--prune` the rows that were found are only listed in the report.

Before writing, the script checks that no deleted title id is left in any table
(`prune verification: ... integrity_check=ok`) and that a copy of the original database is in
`tmp\backup\`.

### Notes

* **Local copy.** Everything happens on `tmp\app.db`; the file goes to the console only with
  `--apply` (plus an md5 check). The original always stays in `tmp\app.db.orig`.
* **contentSize is the only approximate field.** For games on the external HDD the size of `app.pkg`
  is used (via MLSD/LIST: the `SIZE` answer of GoldHEN overflows above 4 GiB). For internal games an
  estimate from `app.json` is used — that is the size of the *download*, while app.db keeps the size
  of the *installed* content, which only the console knows. It does not influence the game showing
  up in the library; `--no-appinfo` switches work on `tbl_appinfo` off completely.
* **`--repair`** only fixes `hddLocation` and `metaDataPath` of rows that already exist (for example
  rows of internal games left after moving to an external HDD). Other values are not touched.
* **`--offline` without FTP.** With `--offline --db <file>` only the local copy is used: `--apply`
  uploads nothing (`offline mode, nothing was uploaded` in the report). The prepared database can be
  uploaded later with `fix_db.exe PS4_IP --db tmp\app.db --apply --yes`.
* **Roll back.** `fix_db.exe --restore tmp\backup\app.db.20260101-120000 --apply` (or
  `tmp\app.db.orig`) puts the database back.

### Files

```
fix_db.exe      the prebuilt program: run_check.bat / run_apply.bat start it with the right options
run_check.bat   check only, nothing is written to the console
run_apply.bat   write app.db back to the console
README.md       this file
LICENSE         MIT license
tmp\            created on the first run: app.db, app.db.orig, backup\, appmeta\, reports

fix_db.py       the source: FTP, param.sfo, the layout of tbl_appbrowse_*, row writing
appinfo.py      a pseudo app.info for tbl_appinfo
sfo\            param.sfo reader (MIT, Copyright (c) 2016 cologler)
build_exe.bat   rebuild fix_db.exe (PyInstaller)
make_dist.bat   build the release archive in dist\ and refresh SHA256SUMS.txt
make_dist.ps1   what make_dist.bat calls
SHA256SUMS.txt  the hash of fix_db.exe
```

This repository is called **PS4_db_rebuilder**. The second tool of the project lives in its own
repository, **PS4_hide_icons** (desktop icons): it ships the same `fix_db.exe` build as a helper
program, so after a rebuild copy the new exe into both repositories.

## Building the exe file

Python 3.8+ and PyInstaller are required:

```
python -m pip install pyinstaller
build_exe.bat
```

The script builds `fix_db.exe` next to the sources (`pyinstaller --onefile --console --clean`);
the `build\` folder is not committed. To run from the sources:
`python fix_db.py 192.0.2.10 --db tmp\app.db`.

The archive of the Releases section is built separately:

```
make_dist.bat   -> dist\fix_db.zip, dist\SHA256SUMS.txt
```

## Checksums

```
certutil -hashfile fix_db.exe SHA256
```

Compare the result with `SHA256SUMS.txt`. The exe is built with PyInstaller and is not code
signed, so SmartScreen may show "Windows protected your PC": choose More info → Run anyway.