#!/usr/bin/env python3
"""
Консольное приложение для расчёта дневной и ночной активности птиц.

Входные данные: файлы вида a230930a.txt в директории source (по умолчанию).
Каждая строка: дата;время;16 значений каналов;длинная строка нулей.

Дневная активность для дня D:
    от (рассвет D + сдвиг_нач_день) до (закат D + сдвиг_кон_день),
где сдвиг_нач_день — минуты ДО рассвета (отрицательное = после рассвета),
    сдвиг_кон_день — минуты ПОСЛЕ заката (отрицательное = до заката).

Ночная активность для дня D — в одном из двух режимов:
  - "rest" (остаток суток): от конца дневной активности дня D
    до начала дневной активности дня D+1;
  - "custom": от (закат D + сдвиг_нач_ночь) до
    (рассвет D+1 + сдвиг_кон_ночь),
    где сдвиг_нач_ночь — минуты ДО заката,
    сдвиг_кон_ночь — минуты ПОСЛЕ рассвета.

Ночь приписывается дню её начала
(начало в файле дня D, конец в файле дня D+1).

Время восхода/заката считается по широте/долготе
и смещению UTC.

Настройки сохраняются в файл settings.json рядом со скриптом
и при следующих запусках предлагается изменить их по очереди.

Исключаемые интервалы могут быть:
  - общими для всех дней;
  - уникальными для каждого дня
    (файл exclusions_daily.csv рядом со скриптом).
"""

import csv
import glob
import json
import os
import re
import sys
from datetime import date, datetime, time, timedelta, timezone

import questionary
from astral import LocationInfo
from astral.sun import sun


NUM_CHANNELS = 16

DEFAULT_SOURCE_DIR = "source"
DEFAULT_OUTPUT = "bird_activity_daily.csv"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SETTINGS_FILE = os.path.join(
    SCRIPT_DIR,
    "settings.json",
)

EXCLUSIONS_DAILY_FILE = os.path.join(
    SCRIPT_DIR,
    "exclusions_daily.csv",
)


# ===========================================================================
# Парсинг файлов
# ===========================================================================

FILE_RE = re.compile(
    r"^a(\d{2})(\d{2})(\d{2})a\.txt$"
)


def parse_filename_date(fname):
    """Из имени a230930a.txt извлекаем дату 2023-09-30."""

    m = FILE_RE.match(fname)

    if not m:
        return None

    yy, mm, dd = map(int, m.groups())

    year = 2000 + yy

    try:
        return date(year, mm, dd)

    except ValueError:
        return None


def find_source_files(source_dir):
    """
    Возвращает список (дата, путь),
    отсортированный по дате.
    """

    found = []

    for fpath in sorted(
        glob.glob(
            os.path.join(
                source_dir,
                "a*.txt",
            )
        )
    ):

        fname = os.path.basename(fpath)

        d = parse_filename_date(fname)

        if d is not None:
            found.append(
                (d, fpath)
            )

    found.sort(
        key=lambda x: x[0]
    )

    return found


def format_date_ranges(dates):
    """
    Группирует подряд идущие даты
    в интервалы и форматирует строкой.
    """

    if not dates:
        return "нет файлов"

    ranges = []

    start = prev = dates[0]

    for d in dates[1:]:

        if d == prev + timedelta(days=1):
            prev = d

        else:
            ranges.append(
                (start, prev)
            )

            start = prev = d

    ranges.append(
        (start, prev)
    )

    parts = []

    for s, e in ranges:

        if s == e:

            parts.append(
                s.strftime("%d.%m.%Y")
            )

        else:

            parts.append(
                f"{s.strftime('%d.%m.%Y')} – "
                f"{e.strftime('%d.%m.%Y')}"
            )

    return ", ".join(parts)


def load_rows(fpath):
    """
    Читает файл.

    Возвращает список:
        (datetime, [16 значений])
    """

    rows = []

    with open(
        fpath,
        encoding="utf-8",
    ) as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            parts = line.split(";")

            if len(parts) < 2 + NUM_CHANNELS:
                continue

            date_str = parts[0]
            time_str = parts[1]

            try:

                d, m, y = date_str.split(".")
                h, mi, s = time_str.split(":")

                dt = datetime(
                    int(y),
                    int(m),
                    int(d),
                    int(h),
                    int(mi),
                    int(s),
                )

            except ValueError:
                continue

            try:

                values = [
                    int(v)
                    for v in parts[
                        2:2 + NUM_CHANNELS
                    ]
                ]

            except ValueError:
                continue

            rows.append(
                (dt, values)
            )

    return rows


# ===========================================================================
# Восход / закат
# ===========================================================================

def get_sun_times(
    lat,
    lon,
    utc_offset_hours,
    day,
):
    """
    Возвращает:
        (восход, закат)

    в локальном времени
    в виде naive datetime.
    """

    tz = timezone(
        timedelta(
            hours=utc_offset_hours
        )
    )

    loc = LocationInfo(
        "loc",
        "loc",
        "UTC",
        lat,
        lon,
    )

    s = sun(
        loc.observer,
        date=day,
        tzinfo=tz,
    )

    return (
        s["sunrise"].replace(
            tzinfo=None
        ),
        s["sunset"].replace(
            tzinfo=None
        ),
    )


# ===========================================================================
# Настройки
# ===========================================================================

def default_settings():
    return {

        "lat": None,

        "lon": None,

        "utc_offset": None,

        "day_start_shift": 0,

        "day_end_shift": 0,

        "night_mode": "rest",

        "night_start_shift": 0,

        "night_end_shift": 0,

        "exclusions_mode": "common",

        "exclusions": [],
    }


def load_settings():

    if os.path.exists(
        SETTINGS_FILE
    ):

        try:

            with open(
                SETTINGS_FILE,
                encoding="utf-8",
            ) as f:

                data = json.load(f)

            s = default_settings()

            s.update(data)

            return s

        except (
            json.JSONDecodeError,
            OSError,
        ):

            print(
                "Не удалось прочитать файл "
                "настроек, начнём с нуля."
            )

    return default_settings()


def save_settings(settings):

    with open(
        SETTINGS_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            settings,
            f,
            ensure_ascii=False,
            indent=2,
        )


def format_exclusions(exclusions):

    if not exclusions:
        return "нет"

    return ", ".join(
        f"{a}-{b}"
        for a, b in exclusions
    )


def describe_settings(
    s,
    dates=None,
):
    """
    Формирует описание текущих настроек.

    Для индивидуальных исключений
    показывает интервалы каждого дня.
    """

    if s["night_mode"] == "rest":

        night_desc = "остаток суток"

    else:

        night_desc = (
            "отдельные границы "
            f"(нач {s['night_start_shift']} мин "
            "до заката, "
            f"кон {s['night_end_shift']} мин "
            "после рассвета)"
        )

    lines = [

        f"  Широта: {s['lat']}",

        f"  Долгота: {s['lon']}",

        f"  Смещение от UTC (ч): "
        f"{s['utc_offset']}",

        "  Дневная активность: "
        f"начало {s['day_start_shift']} мин "
        "до рассвета, "
        f"конец {s['day_end_shift']} мин "
        "после заката",

        f"  Ночная активность: "
        f"{night_desc}",
    ]

    # ------------------------------------------------------------------
    # Общие исключения
    # ------------------------------------------------------------------

    if s["exclusions_mode"] == "common":

        lines.append(
            "  Исключаемые интервалы: "
            + format_exclusions(
                s["exclusions"]
            )
        )

    # ------------------------------------------------------------------
    # Индивидуальные исключения
    # ------------------------------------------------------------------

    else:

        lines.append(
            "  Исключаемые интервалы: "
            "индивидуальные по дням"
        )

        daily_exclusions = (
            load_exclusions_daily()
        )

        if dates:

            for d in dates:

                intervals = (
                    daily_exclusions.get(
                        d,
                        [],
                    )
                )

                if intervals:

                    formatted = (
                        format_exclusions(
                            intervals
                        )
                    )

                else:

                    formatted = "нет"

                lines.append(
                    f"    {d.strftime('%d.%m.%Y')}: "
                    f"{formatted}"
                )

        elif daily_exclusions:

            for d in sorted(
                daily_exclusions
            ):

                intervals = (
                    daily_exclusions[d]
                )

                formatted = (
                    format_exclusions(
                        intervals
                    )
                    if intervals
                    else "нет"
                )

                lines.append(
                    f"    {d.strftime('%d.%m.%Y')}: "
                    f"{formatted}"
                )

        else:

            lines.append(
                "    файл exclusions_daily.csv "
                "пуст или отсутствует"
            )

    return "\n".join(lines)


# ===========================================================================
# Валидаторы
# ===========================================================================

def validate_float(text):

    try:

        float(text)

        return True

    except ValueError:

        return "Введите число."


def validate_int(text):

    try:

        int(text)

        return True

    except ValueError:

        return "Введите целое число."


def validate_interval(text):

    if not re.match(
        r"^\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}$",
        text,
    ):

        return "Формат: HH:MM-HH:MM"

    m = re.match(
        r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$",
        text,
    )

    h1, m1, h2, m2 = map(
        int,
        m.groups(),
    )

    if not (
        0 <= h1 <= 23
        and 0 <= m1 <= 59
        and 0 <= h2 <= 23
        and 0 <= m2 <= 59
    ):

        return (
            "Время должно быть "
            "в диапазоне 00:00-23:59."
        )

    return True


# ===========================================================================
# Интерактивный интерфейс
# ===========================================================================

def ask_float(
    prompt,
    default=None,
):

    default_str = (
        ""
        if default is None
        else str(default)
    )

    value = questionary.text(
        prompt,
        default=default_str,
        validate=validate_float,
    ).ask()

    if value is None:
        raise KeyboardInterrupt

    return float(value)


def ask_int(
    prompt,
    default=None,
):

    default_str = (
        ""
        if default is None
        else str(default)
    )

    value = questionary.text(
        prompt,
        default=default_str,
        validate=validate_int,
    ).ask()

    if value is None:
        raise KeyboardInterrupt

    return int(value)


def ask_shift_minutes(
    prompt,
    default=None,
):

    return ask_int(
        prompt,
        default,
    )


def ask_change(
    title,
    current_value,
    input_prompt,
    value_type="text",
):
    """
    Для существующей настройки:

        Не менять
        Изменить
    """

    current = (
        "не задано"
        if current_value is None
        else str(current_value)
    )

    print()
    print(title)
    print(
        f"  Текущее значение: {current}"
    )

    action = questionary.select(
        "Что сделать?",
        choices=[
            "Не менять",
            "Изменить",
        ],
    ).ask()

    if action is None:
        raise KeyboardInterrupt

    if action == "Не менять":
        return current_value

    if value_type == "float":

        return ask_float(
            input_prompt,
            current_value,
        )

    if value_type == "int":

        return ask_int(
            input_prompt,
            current_value,
        )

    value = questionary.text(
        input_prompt,
        default=(
            ""
            if current_value is None
            else str(current_value)
        ),
    ).ask()

    if value is None:
        raise KeyboardInterrupt

    return value


# ===========================================================================
# Исключения
# ===========================================================================

def ask_exclusions_common():
    """
    Ввод общих исключаемых интервалов.
    """

    print()
    print("Исключаемые интервалы")
    print("---------------------")
    print("Формат: HH:MM-HH:MM")
    print("Например: 08:00-10:30")
    print("Пустая строка — закончить.")

    intervals = []

    while True:

        raw = questionary.text(
            "Интервал:"
        ).ask()

        if raw is None:
            raise KeyboardInterrupt

        raw = raw.strip()

        if not raw:
            break

        if validate_interval(raw) is not True:

            print(
                "Неверный формат."
            )

            continue

        m = re.match(
            r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$",
            raw,
        )

        h1, m1, h2, m2 = map(
            int,
            m.groups(),
        )

        intervals.append(
            [
                f"{h1:02d}:{m1:02d}",
                f"{h2:02d}:{m2:02d}",
            ]
        )

        print(
            "  Добавлено: "
            f"{h1:02d}:{m1:02d}-"
            f"{h2:02d}:{m2:02d}"
        )

    return intervals


def create_exclusions_template(
    dates,
):
    """
    Создаёт exclusions_daily.csv.
    """

    with open(
        EXCLUSIONS_DAILY_FILE,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.writer(
            f,
            delimiter=";",
        )

        writer.writerow(
            [
                "date",
                "interval1",
                "interval2",
                "interval3",
                "interval4",
                "interval5",
            ]
        )

        for d in dates:

            writer.writerow(
                [
                    d.strftime(
                        "%Y-%m-%d"
                    ),
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )

    print()
    print(
        "Создан файл:"
    )
    print(
        f"  {EXCLUSIONS_DAILY_FILE}"
    )
    print()
    print(
        "Заполните интервалы "
        "в формате HH:MM-HH:MM."
    )


def load_exclusions_daily():
    """
    Читает exclusions_daily.csv.

    Возвращает:

        {
            date: [
                ["HH:MM", "HH:MM"],
                ...
            ]
        }
    """

    result = {}

    if not os.path.exists(
        EXCLUSIONS_DAILY_FILE
    ):
        return result

    with open(
        EXCLUSIONS_DAILY_FILE,
        encoding="utf-8",
    ) as f:

        reader = csv.reader(
            f,
            delimiter=";",
        )

        header = next(
            reader,
            None,
        )

        if header is None:
            return result

        for row in reader:

            if (
                not row
                or not row[0].strip()
            ):
                continue

            try:

                d = datetime.strptime(
                    row[0].strip(),
                    "%Y-%m-%d",
                ).date()

            except ValueError:

                continue

            intervals = []

            for cell in row[1:]:

                cell = cell.strip()

                if not cell:
                    continue

                m = re.match(
                    r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$",
                    cell,
                )

                if not m:
                    continue

                h1, m1, h2, m2 = map(
                    int,
                    m.groups(),
                )

                if not (
                    0 <= h1 <= 23
                    and 0 <= m1 <= 59
                    and 0 <= h2 <= 23
                    and 0 <= m2 <= 59
                ):
                    continue

                intervals.append(
                    [
                        f"{h1:02d}:{m1:02d}",
                        f"{h2:02d}:{m2:02d}",
                    ]
                )

            result[d] = intervals

    return result


def show_loaded_daily_exclusions(
    dates,
    daily_exclusions,
):
    """
    Показывает интервалы, которые были
    прочитаны из exclusions_daily.csv.
    """

    print()
    print("=" * 60)
    print("ЗАГРУЖЕННЫЕ ИСКЛЮЧЕНИЯ")
    print("=" * 60)

    for d in dates:

        intervals = (
            daily_exclusions.get(
                d,
                [],
            )
        )

        if intervals:

            print(
                f"  {d.strftime('%d.%m.%Y')}: "
                f"{format_exclusions(intervals)}"
            )

        else:

            print(
                f"  {d.strftime('%d.%m.%Y')}: "
                "нет"
            )

    print()


def ask_exclusions(dates):
    """
    Выбор способа задания исключений.

    common:
        интервалы одинаковые для всех дней.

    daily:
        интервалы задаются в exclusions_daily.csv
        отдельно для каждого дня.

    ВАЖНО:
        существующий exclusions_daily.csv никогда не
        перезаписывается автоматически.
    """

    print()

    choice = questionary.select(
        "Как задавать исключаемые интервалы?",
        choices=[
            "Одинаковые для всех дней",
            "Отдельно для каждого дня",
        ],
    ).ask()

    if choice is None:
        raise KeyboardInterrupt

    # ===============================================================
    # ОБЩИЕ ИНТЕРВАЛЫ
    # ===============================================================

    if choice == "Одинаковые для всех дней":

        return (
            "common",
            ask_exclusions_common(),
        )

    # ===============================================================
    # ИНДИВИДУАЛЬНЫЕ ИНТЕРВАЛЫ
    # ===============================================================

    # ---------------------------------------------------------------
    # Если файла ещё нет — создаём шаблон.
    # Если файл уже есть — НЕ ТРОГАЕМ ЕГО.
    # ---------------------------------------------------------------

    if not os.path.exists(
        EXCLUSIONS_DAILY_FILE
    ):

        create_exclusions_template(
            dates
        )

    else:

        print()
        print(
            "Файл индивидуальных исключений "
            "уже существует:"
        )
        print(
            f"  {EXCLUSIONS_DAILY_FILE}"
        )

        current_exclusions = (
            load_exclusions_daily()
        )

        print()

        print(
            "Текущие интервалы:"
        )

        for d in dates:

            intervals = (
                current_exclusions.get(
                    d,
                    [],
                )
            )

            if intervals:

                print(
                    f"  {d.strftime('%d.%m.%Y')}: "
                    f"{format_exclusions(intervals)}"
                )

            else:

                print(
                    f"  {d.strftime('%d.%m.%Y')}: "
                    "нет"
                )

    # ===============================================================
    # Предлагаем отредактировать файл
    # ===============================================================

    print()
    print("=" * 60)
    print("ИНДИВИДУАЛЬНЫЕ ИСКЛЮЧЕНИЯ")
    print("=" * 60)
    print()
    print(
        "Откройте файл:"
    )
    print(
        f"  {EXCLUSIONS_DAILY_FILE}"
    )
    print()
    print(
        "Измените нужные интервалы."
    )
    print(
        "Существующие значения можно оставить "
        "без изменений."
    )
    print()
    print(
        "Формат: HH:MM-HH:MM"
    )
    print(
        "Например: 08:00-10:30"
    )
    print()
    print(
        "Для дня без исключений оставьте "
        "ячейку пустой."
    )
    print()
    print(
        "После изменения сохраните файл "
        "и вернитесь в программу."
    )
    print()

    questionary.press_any_key_to_continue(
        "Нажмите любую клавишу "
        "после сохранения файла..."
    ).ask()

    # ===============================================================
    # Перечитываем файл
    # ===============================================================

    daily_exclusions = (
        load_exclusions_daily()
    )

    # ===============================================================
    # Показываем результат
    # ===============================================================

    show_loaded_daily_exclusions(
        dates,
        daily_exclusions,
    )

    questionary.press_any_key_to_continue(
        "Нажмите любую клавишу "
        "для продолжения расчёта..."
    ).ask()

    return (
        "daily",
        None,
    )


# ===========================================================================
# Первоначальная настройка
# ===========================================================================

def ask_all_settings(
    dates,
):
    """
    Первый запуск программы.
    Все настройки задаются последовательно.
    """

    s = default_settings()

    print()
    print("=" * 50)
    print("НАСТРОЙКА ПРОГРАММЫ")
    print("=" * 50)

    # ------------------------------------------------------------------
    # Координаты
    # ------------------------------------------------------------------

    print()
    print("--- Координаты и часовой пояс ---")

    s["lat"] = ask_float(
        "Широта:"
    )

    s["lon"] = ask_float(
        "Долгота:"
    )

    s["utc_offset"] = ask_float(
        "Смещение от UTC в часах:"
    )

    # ------------------------------------------------------------------
    # День
    # ------------------------------------------------------------------

    print()
    print("--- Дневная активность ---")

    s["day_start_shift"] = (
        ask_shift_minutes(
            "Начало дня — минут до рассвета "
            "(отрицательное = после рассвета):"
        )
    )

    s["day_end_shift"] = (
        ask_shift_minutes(
            "Конец дня — минут после заката "
            "(отрицательное = до заката):"
        )
    )

    # ------------------------------------------------------------------
    # Ночь
    # ------------------------------------------------------------------

    print()
    print("--- Ночная активность ---")

    night_choice = questionary.select(
        "Как считать ночную активность?",
        choices=[
            "Весь остальной период считать ночью",
            "Задать отдельные границы",
        ],
    ).ask()

    if night_choice is None:
        raise KeyboardInterrupt

    if (
        night_choice
        == "Весь остальной период считать ночью"
    ):

        s["night_mode"] = "rest"

    else:

        s["night_mode"] = "custom"

        s["night_start_shift"] = (
            ask_shift_minutes(
                "Начало ночи — минут до заката "
                "(отрицательное = после заката):"
            )
        )

        s["night_end_shift"] = (
            ask_shift_minutes(
                "Конец ночи — минут после рассвета "
                "следующего дня "
                "(отрицательное = до рассвета):"
            )
        )

    # ------------------------------------------------------------------
    # Исключения
    # ------------------------------------------------------------------

    print()
    print("--- Исключаемые интервалы ---")

    (
        s["exclusions_mode"],
        s["exclusions"],
    ) = ask_exclusions(
        dates
    )

    return s


# ===========================================================================
# Изменение существующих настроек
# ===========================================================================

def maybe_edit_settings(
    s,
    dates,
):
    """
    Если settings.json отсутствует —
    создаём настройки с нуля.

    Если существует —
    показываем текущие значения и
    предлагаем изменить их по очереди.
    """

    # ==================================================================
    # Первый запуск
    # ==================================================================

    if not os.path.exists(
        SETTINGS_FILE
    ):

        return ask_all_settings(
            dates
        )

    # ==================================================================
    # Существующие настройки
    # ==================================================================

    print()
    print("=" * 50)
    print("ТЕКУЩИЕ НАСТРОЙКИ")
    print("=" * 50)

    print(
        describe_settings(
            s,
            dates,
        )
    )

    print()

    action = questionary.select(
        "Что сделать с настройками?",
        choices=[
            "Оставить всё как есть",
            "Изменить настройки",
        ],
    ).ask()

    if action is None:
        raise KeyboardInterrupt

    if action == "Оставить всё как есть":

        return s

    print()
    print("=" * 50)
    print("ИЗМЕНЕНИЕ НАСТРОЕК")
    print("=" * 50)

    # ------------------------------------------------------------------
    # Широта
    # ------------------------------------------------------------------

    s["lat"] = ask_change(
        "Широта",
        s["lat"],
        "Новая широта:",
        value_type="float",
    )

    # ------------------------------------------------------------------
    # Долгота
    # ------------------------------------------------------------------

    s["lon"] = ask_change(
        "Долгота",
        s["lon"],
        "Новая долгота:",
        value_type="float",
    )

    # ------------------------------------------------------------------
    # UTC
    # ------------------------------------------------------------------

    s["utc_offset"] = ask_change(
        "Смещение от UTC",
        s["utc_offset"],
        "Новое смещение от UTC:",
        value_type="float",
    )

    # ------------------------------------------------------------------
    # Начало дня
    # ------------------------------------------------------------------

    s["day_start_shift"] = ask_change(
        "Граница начала дневной активности",
        s["day_start_shift"],
        "Новый сдвиг в минутах:",
        value_type="int",
    )

    # ------------------------------------------------------------------
    # Конец дня
    # ------------------------------------------------------------------

    s["day_end_shift"] = ask_change(
        "Граница конца дневной активности",
        s["day_end_shift"],
        "Новый сдвиг в минутах:",
        value_type="int",
    )

    # ------------------------------------------------------------------
    # Ночь
    # ------------------------------------------------------------------

    print()

    night_action = questionary.select(
        "Что делать с режимом ночной активности?",
        choices=[
            "Не менять",
            "Весь остальной период считать ночью",
            "Задать отдельные границы",
        ],
    ).ask()

    if night_action is None:
        raise KeyboardInterrupt

    if (
        night_action
        == "Весь остальной период считать ночью"
    ):

        s["night_mode"] = "rest"

    elif (
        night_action
        == "Задать отдельные границы"
    ):

        s["night_mode"] = "custom"

        s["night_start_shift"] = (
            ask_change(
                "Граница начала ночи",
                s["night_start_shift"],
                "Новый сдвиг начала ночи "
                "в минутах:",
                value_type="int",
            )
        )

        s["night_end_shift"] = (
            ask_change(
                "Граница конца ночи",
                s["night_end_shift"],
                "Новый сдвиг конца ночи "
                "в минутах:",
                value_type="int",
            )
        )

    # ------------------------------------------------------------------
    # Исключения
    # ------------------------------------------------------------------

    print()

    exclusion_action = questionary.select(
        "Что делать с исключаемыми интервалами?",
        choices=[
            "Не менять",
            "Настроить заново",
        ],
    ).ask()

    if exclusion_action is None:
        raise KeyboardInterrupt

    if (
        exclusion_action
        == "Настроить заново"
    ):

        (
            s["exclusions_mode"],
            s["exclusions"],
        ) = ask_exclusions(
            dates
        )

    return s


# ===========================================================================
# Основная логика
# ===========================================================================

def parse_exclusion_time(
    s,
):
    h, m = s.split(":")

    return time(
        int(h),
        int(m),
    )


def in_exclusion(
    dt,
    exclusions,
):
    """
    True, если момент времени dt
    попадает в один из исключаемых
    интервалов.
    """

    t = dt.time()

    for start_s, end_s in exclusions:

        start = parse_exclusion_time(
            start_s
        )

        end = parse_exclusion_time(
            end_s
        )

        if start <= end:

            if start <= t <= end:
                return True

        else:

            # Интервал переходит через полночь

            if t >= start or t <= end:
                return True

    return False


def sum_interval(
    rows_by_day,
    start_dt,
    end_dt,
    exclusions,
):
    """
    Суммирует значения по каналам
    в [start_dt, end_dt)
    с учётом исключений.
    """

    total = [
        0
        for _ in range(
            NUM_CHANNELS
        )
    ]

    # Интервал может пересекать
    # несколько дней.

    cur = start_dt

    while cur < end_dt:

        day_rows = rows_by_day.get(
            cur.date()
        )

        if day_rows:

            for dt, vals in day_rows:

                if (
                    start_dt <= dt < end_dt
                    and not in_exclusion(
                        dt,
                        exclusions,
                    )
                ):

                    for ch in range(
                        NUM_CHANNELS
                    ):

                        total[ch] += vals[ch]

        cur += timedelta(
            days=1
        )

    return total


# ===========================================================================
# MAIN
# ===========================================================================

def main():

    source_dir = (
        DEFAULT_SOURCE_DIR
    )

    if len(sys.argv) > 1:
        source_dir = sys.argv[1]

    # ------------------------------------------------------------------
    # Проверка директории
    # ------------------------------------------------------------------

    if not os.path.isdir(
        source_dir
    ):

        print(
            f"Директория "
            f"'{source_dir}' не найдена."
        )

        sys.exit(1)

    # ------------------------------------------------------------------
    # Поиск файлов
    # ------------------------------------------------------------------

    files = find_source_files(
        source_dir
    )

    if not files:

        print(
            f"В директории "
            f"'{source_dir}' не найдено "
            f"файлов вида aYYMMDDa.txt."
        )

        sys.exit(1)

    dates = [
        d
        for d, _ in files
    ]

    print(
        f"Найдено файлов: "
        f"{len(files)}"
    )

    print(
        f"Даты: "
        f"{format_date_ranges(dates)}"
    )

    # ------------------------------------------------------------------
    # Настройки
    # ------------------------------------------------------------------

    settings = load_settings()

    settings = maybe_edit_settings(
        settings,
        dates,
    )

    save_settings(
        settings
    )

    # ------------------------------------------------------------------
    # Получаем настройки
    # ------------------------------------------------------------------

    lat = settings["lat"]

    lon = settings["lon"]

    utc_offset = settings[
        "utc_offset"
    ]

    day_start_shift = settings[
        "day_start_shift"
    ]

    day_end_shift = settings[
        "day_end_shift"
    ]

    night_mode = settings[
        "night_mode"
    ]

    night_start_shift = settings[
        "night_start_shift"
    ]

    night_end_shift = settings[
        "night_end_shift"
    ]

    exclusions_mode = settings[
        "exclusions_mode"
    ]

    common_exclusions = settings[
        "exclusions"
    ]

    # ------------------------------------------------------------------
    # Индивидуальные исключения
    # ------------------------------------------------------------------

    daily_exclusions = {}

    if exclusions_mode == "daily":

        daily_exclusions = (
            load_exclusions_daily()
        )

        if not daily_exclusions:

            print()

            print(
                "Внимание: файл "
                f"{EXCLUSIONS_DAILY_FILE} "
                "пуст или не содержит данных."
            )

    # ------------------------------------------------------------------
    # Загрузка данных
    # ------------------------------------------------------------------

    print()
    print(
        "Загрузка данных..."
    )

    rows_by_day = {}

    for d, fpath in files:

        rows_by_day[d] = (
            load_rows(fpath)
        )

    # ------------------------------------------------------------------
    # Расчёт
    # ------------------------------------------------------------------

    print(
        "Расчёт активности..."
    )

    results = {}

    for i, d in enumerate(
        dates
    ):

        sunrise, sunset = (
            get_sun_times(
                lat,
                lon,
                utc_offset,
                d,
            )
        )

        next_day = (
            d + timedelta(
                days=1
            )
        )

        next_sunrise, _ = (
            get_sun_times(
                lat,
                lon,
                utc_offset,
                next_day,
            )
        )

        # --------------------------------------------------------------
        # Дневная активность
        # --------------------------------------------------------------

        day_start = (
            sunrise
            - timedelta(
                minutes=day_start_shift
            )
        )

        day_end = (
            sunset
            + timedelta(
                minutes=day_end_shift
            )
        )

        # --------------------------------------------------------------
        # Ночная активность
        # --------------------------------------------------------------

        if night_mode == "rest":

            # Ночь =
            # от конца дневной активности
            # дня D
            # до начала дневной активности
            # дня D+1.

            next_day_start = (
                next_sunrise
                - timedelta(
                    minutes=day_start_shift
                )
            )

            night_start = day_end

            night_end = (
                next_day_start
            )

        else:

            night_start = (
                sunset
                - timedelta(
                    minutes=night_start_shift
                )
            )

            night_end = (
                next_sunrise
                + timedelta(
                    minutes=night_end_shift
                )
            )

        # --------------------------------------------------------------
        # Исключения для этого дня
        # --------------------------------------------------------------

        if exclusions_mode == "daily":

            exclusions = (
                daily_exclusions.get(
                    d,
                    [],
                )
            )

        else:

            exclusions = (
                common_exclusions
            )

        # --------------------------------------------------------------
        # Суммирование
        # --------------------------------------------------------------

        day_sum = sum_interval(
            rows_by_day,
            day_start,
            day_end,
            exclusions,
        )

        night_sum = sum_interval(
            rows_by_day,
            night_start,
            night_end,
            exclusions,
        )

        results[d] = {
            "day": day_sum,
            "night": night_sum,
        }

    # ------------------------------------------------------------------
    # Запись результата
    # ------------------------------------------------------------------

    output = DEFAULT_OUTPUT

    with open(
        output,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.writer(
            f,
            delimiter=";",
        )

        header = [
            "date"
        ]

        for ch in range(
            1,
            NUM_CHANNELS + 1,
        ):

            header.append(
                f"day_ch{ch}"
            )

        for ch in range(
            1,
            NUM_CHANNELS + 1,
        ):

            header.append(
                f"night_ch{ch}"
            )

        writer.writerow(
            header
        )

        for d in dates:

            row = [
                d.strftime(
                    "%Y-%m-%d"
                )
            ]

            row += results[d][
                "day"
            ]

            row += results[d][
                "night"
            ]

            writer.writerow(
                row
            )

    # ------------------------------------------------------------------
    # Готово
    # ------------------------------------------------------------------

    print()
    print(
        f"Готово! Результат записан "
        f"в '{output}'."
    )

    print(
        f"Обработано дней: "
        f"{len(dates)}"
    )


if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print(
            "Программа остановлена пользователем."
        )

