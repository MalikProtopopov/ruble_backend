# Модуль «Документы» — руководство для фронтенда админки

Документ для фронтенд-разработчика: полный контракт API, типы данных, структура таблицы, формы, жизненный цикл документа, WYSIWYG-редактор.

---

## 1. Назначение

Юридические и корпоративные документы (политика конфиденциальности, оферта, правила платформы и т.п.) с:

- **Статусами** (черновик → опубликован → архив)
- **Slug** для URL на публичном сайте
- **HTML-контентом** (через WYSIWYG-редактор)
- **Опциональным файлом** (PDF, DOCX и др.)
- **Optimistic locking** (защита от конкурентного редактирования)

---

## 2. API-эндпоинты

Авторизация: Bearer JWT (admin). Базовый путь: `/api/v1/admin/documents`.

### 2.1. Список документов

**GET** `/api/v1/admin/documents`

| Параметр | Тип | Описание |
|----------|-----|----------|
| `status` | string | Фильтр: `draft`, `published` или `archived` |
| `search` | string | Поиск по названию |
| `limit` | int | 1–100, по умолчанию 20 |
| `cursor` | string | Курсор для следующей страницы |

**Ответ:**

```json
{
  "data": [
    {
      "id": "019...",
      "title": "Политика конфиденциальности",
      "slug": "privacy-policy",
      "excerpt": "Краткое описание...",
      "content": "<p>Полный HTML текст...</p>",
      "status": "published",
      "document_version": "1.0",
      "document_date": "2026-03-01",
      "published_at": "2026-03-01T12:00:00Z",
      "file_url": "https://backend.porublyu.parmenid.tech/media/documents/abc123.pdf",
      "sort_order": 0,
      "version": 3,
      "created_at": "2026-03-01T10:00:00Z",
      "updated_at": "2026-03-31T15:00:00Z"
    }
  ],
  "pagination": {
    "next_cursor": "eyJpZCI6ICIuLi4ifQ==",
    "has_more": true,
    "total": null
  }
}
```

### 2.2. Создание документа

**POST** `/api/v1/admin/documents`

**Тело запроса:**

```json
{
  "title": "Пользовательское соглашение",
  "slug": "user-agreement",
  "excerpt": "Краткое описание документа",
  "content": "<h1>Соглашение</h1><p>Текст...</p>",
  "status": "draft",
  "document_version": "1.0",
  "document_date": "2026-03-31",
  "sort_order": 0
}
```

| Поле | Тип | Обязательное | Ограничения |
|------|-----|:---:|-------------|
| `title` | string | да | 1–255 символов |
| `slug` | string | да | 2–255 символов, уникален среди неудалённых |
| `excerpt` | string | нет | до 500 символов |
| `content` | string | нет | HTML-текст (из WYSIWYG-редактора) |
| `status` | string | нет | `draft` (по умолчанию), `published`, `archived` |
| `document_version` | string | нет | до 50 символов, напр. `"1.0"`, `"v2.3"` |
| `document_date` | string (date) | нет | Формат `YYYY-MM-DD` |
| `sort_order` | int | нет | По умолчанию 0 |

**Ответ (201):** полный объект документа (как в списке).

**Ошибки:**

| HTTP | Код | Когда |
|:---:|------|-------|
| 409 | `SLUG_ALREADY_EXISTS` | slug уже занят |
| 422 | `INVALID_STATUS` | Невалидный статус |

### 2.3. Получение документа

**GET** `/api/v1/admin/documents/{id}`

**Ответ (200):** полный объект документа.

**Ошибки:** 404 — документ не найден.

### 2.4. Обновление документа

**PATCH** `/api/v1/admin/documents/{id}`

**Тело запроса (все поля кроме `version` опциональны):**

```json
{
  "title": "Обновлённый заголовок",
  "slug": "updated-slug",
  "content": "<p>Обновлённый текст</p>",
  "version": 3
}
```

| Поле | Тип | Обязательное | Описание |
|------|-----|:---:|----------|
| `title` | string | нет | 1–255 символов |
| `slug` | string | нет | 2–255, уникален |
| `excerpt` | string | нет | до 500 символов |
| `content` | string | нет | HTML |
| `status` | string | нет | `draft`, `published`, `archived` |
| `document_version` | string | нет | Версия документа для отображения |
| `document_date` | date | нет | `YYYY-MM-DD` |
| `sort_order` | int | нет | Порядок сортировки |
| **`version`** | **int** | **да** | **Текущая версия с сервера** — для optimistic locking |

**Ошибки:**

| HTTP | Код | Когда |
|:---:|------|-------|
| 404 | `NOT_FOUND` | Документ не найден |
| 409 | `VERSION_CONFLICT` | Документ изменён другим пользователем (details содержит `current_version`) |
| 409 | `SLUG_ALREADY_EXISTS` | Новый slug уже занят |
| 422 | `INVALID_STATUS` | Невалидный статус |

### 2.5. Удаление документа (soft delete)

**DELETE** `/api/v1/admin/documents/{id}`

**Ответ:** 204 No Content.

### 2.6. Публикация

**POST** `/api/v1/admin/documents/{id}/publish`

Переводит документ в статус `published`. Если `published_at` ещё не был установлен — проставляет текущее время.

**Ответ (200):** обновлённый объект документа.

### 2.7. Снятие с публикации

**POST** `/api/v1/admin/documents/{id}/unpublish`

Переводит документ обратно в `draft`. Поле `published_at` **не очищается**.

**Ответ (200):** обновлённый объект документа.

### 2.8. Загрузка файла к документу

**POST** `/api/v1/admin/documents/{id}/file`

**Content-Type:** `multipart/form-data`

| Поле | Тип | Описание |
|------|-----|----------|
| `file` | file (binary) | Файл для загрузки |

**Ограничения:**

| Макс. размер | Допустимые форматы |
|:---:|------|
| 50 МБ | PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT, CSV |

**Ответ (200):** обновлённый объект документа (с заполненным `file_url`).

**Ошибки:**

| HTTP | Код | Когда |
|:---:|------|-------|
| 422 | `INVALID_FILE_FORMAT` | Недопустимый MIME |
| 422 | `FILE_TOO_LARGE` | Файл > 50 МБ |

### 2.9. Удаление файла документа

**DELETE** `/api/v1/admin/documents/{id}/file`

Удаляет файл из S3 и обнуляет `file_url`.

**Ответ (200):** обновлённый объект документа (с `file_url: null`).

**Ошибки:** 422 `NO_FILE` — у документа нет файла.

---

## 3. Публичные эндпоинты (без авторизации)

Базовый путь: `/api/v1/documents`. Только опубликованные документы.

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/v1/documents` | Список (без `content`) |
| GET | `/api/v1/documents/{slug}` | Деталь по slug (с `content`) |

**Ответ списка:**

```json
{
  "data": [
    {
      "slug": "privacy-policy",
      "title": "Политика конфиденциальности",
      "excerpt": "...",
      "document_version": "1.0",
      "document_date": "2026-03-01",
      "published_at": "2026-03-01T12:00:00Z",
      "file_url": "https://..."
    }
  ],
  "pagination": { "next_cursor": null, "has_more": false, "total": null }
}
```

**Ответ детали:** то же + поле `content` (HTML).

---

## 4. Типы данных для фронтенда

```ts
// --- Модель документа ---

interface Document {
  id: string;
  title: string;
  slug: string;
  excerpt: string | null;
  content: string | null;         // HTML из WYSIWYG-редактора
  status: "draft" | "published" | "archived";
  document_version: string | null;
  document_date: string | null;   // "YYYY-MM-DD"
  published_at: string | null;    // ISO 8601
  file_url: string | null;
  sort_order: number;
  version: number;                // для optimistic locking
  created_at: string;
  updated_at: string;
}

// --- Запросы ---

interface DocumentCreateRequest {
  title: string;
  slug: string;
  excerpt?: string;
  content?: string;
  status?: "draft" | "published" | "archived";
  document_version?: string;
  document_date?: string;
  sort_order?: number;
}

interface DocumentUpdateRequest {
  title?: string;
  slug?: string;
  excerpt?: string;
  content?: string;
  status?: "draft" | "published" | "archived";
  document_version?: string;
  document_date?: string;
  sort_order?: number;
  version: number;  // ОБЯЗАТЕЛЬНО
}

// --- Ответы ---

interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    next_cursor: string | null;
    has_more: boolean;
    total: number | null;
  };
}
```

---

## 5. Реализация на фронте

### 5.1. Страница списка документов

**Путь:** `/dashboard/documents`

**Таблица с колонками:**

| Колонка | Поле | Примечание |
|---------|------|------------|
| Название | `title` | Ссылка на форму редактирования |
| Slug | `slug` | Моноширинный шрифт |
| Статус | `status` | Бейдж: зелёный=published, серый=draft, жёлтый=archived |
| Версия | `document_version` | Текстовое, может быть null |
| Дата документа | `document_date` | Форматировать как `DD.MM.YYYY` |
| Файл | `file_url` | Иконка/ссылка если есть, «—» если нет |
| Обновлён | `updated_at` | Относительная дата или `DD.MM.YYYY HH:mm` |

**Фильтры:**
- Select по статусу: Все / Черновик / Опубликован / Архив
- Текстовый поиск по названию

**Действия:**
- Кнопка «Создать документ» → форма создания
- По клику на строку → форма редактирования

**Пагинация:** курсорная, кнопка «Загрузить ещё» или infinite scroll.

### 5.2. Форма создания/редактирования

**Поля формы:**

| Поле | Компонент | Примечание |
|------|-----------|------------|
| Название | Input | Обязательное |
| Slug | Input | Обязательное, автогенерация из title (транслитерация) |
| Краткое описание | Textarea | До 500 символов |
| Содержимое | **RichTextEditor** (TipTap) | HTML, см. раздел 6 |
| Статус | Select | draft / published / archived |
| Версия документа | Input | Текстовая, напр. "1.0" |
| Дата документа | DatePicker | Юридическая/отчётная дата |
| Порядок сортировки | Input (number) | По умолчанию 0 |
| Файл | FileUpload | PDF/DOCX/..., отдельные эндпоинты upload/delete |

**Кнопки действий:**
- «Сохранить» → `POST` (создание) или `PATCH` (обновление, с `version`)
- «Опубликовать» → `POST /documents/{id}/publish`
- «В черновик» → `POST /documents/{id}/unpublish`
- «Удалить» → `DELETE /documents/{id}` (с подтверждением)

### 5.3. Optimistic locking — обработка конфликтов

При сохранении всегда передавать текущий `version` из загруженного документа.

```ts
async function saveDocument(id: string, data: Partial<Document>, currentVersion: number) {
  try {
    const response = await api.patch(`/api/v1/admin/documents/${id}`, {
      ...data,
      version: currentVersion,
    });
    return response.data;
  } catch (error) {
    if (error.response?.data?.error?.details?.code === "VERSION_CONFLICT") {
      // Показать уведомление: "Документ был изменён другим пользователем"
      // Предложить перезагрузить страницу
      const serverVersion = error.response.data.error.details.current_version;
      toast.error(`Конфликт версий. Текущая версия на сервере: ${serverVersion}`);
    }
    throw error;
  }
}
```

### 5.4. Загрузка файла к документу

**Не через медиатеку**, а отдельным file input:

```ts
async function uploadDocumentFile(documentId: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await api.post(
    `/api/v1/admin/documents/${documentId}/file`,
    formData
    // НЕ задавать Content-Type — браузер сам
  );
  return response.data; // обновлённый Document с file_url
}

async function deleteDocumentFile(documentId: string) {
  const response = await api.delete(
    `/api/v1/admin/documents/${documentId}/file`
  );
  return response.data;
}
```

**Допустимые форматы для `accept` в input:**

```ts
const DOCUMENT_FILE_ACCEPT =
  ".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv";
```

**Важно:** файл можно загрузить **только после создания документа** (нужен `id`). В форме создания блок загрузки файла показывать как disabled или скрытый — с подсказкой «Сначала сохраните документ».

### 5.5. Автогенерация slug

Рекомендация для UX: при вводе `title` автоматически генерировать `slug` (транслитерация + kebab-case). Позволять ручное редактирование.

```ts
function generateSlug(title: string): string {
  return title
    .toLowerCase()
    .replace(/[а-яё]/g, (ch) => {
      const map: Record<string, string> = {
        а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "yo",
        ж: "zh", з: "z", и: "i", й: "y", к: "k", л: "l", м: "m",
        н: "n", о: "o", п: "p", р: "r", с: "s", т: "t", у: "u",
        ф: "f", х: "kh", ц: "ts", ч: "ch", ш: "sh", щ: "shch",
        ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya",
      };
      return map[ch] || ch;
    })
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}
```

---

## 6. WYSIWYG-редактор (TipTap)

Поле `content` хранит **HTML-строку**. Для редактирования нужен WYSIWYG-редактор. Рекомендуемый стек — **TipTap 3**.

### 6.1. Зависимости

```json
{
  "@tiptap/react": "^3.15.3",
  "@tiptap/starter-kit": "^3.15.3",
  "@tiptap/extension-link": "^3.15.3",
  "@tiptap/extension-image": "^3.15.3",
  "@tiptap/extension-placeholder": "^3.15.3",
  "@tiptap/extension-text-align": "^3.15.3",
  "@tiptap/extension-underline": "^3.15.3",
  "@tiptap/extension-highlight": "^3.15.3",
  "@tiptap/pm": "^3.15.3",
  "dompurify": "^3.3.1",
  "@types/dompurify": "^3.0.5"
}
```

### 6.2. Расширения TipTap

```ts
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import Image from "@tiptap/extension-image";
import Placeholder from "@tiptap/extension-placeholder";
import TextAlign from "@tiptap/extension-text-align";
import Underline from "@tiptap/extension-underline";
import Highlight from "@tiptap/extension-highlight";

const extensions = [
  StarterKit.configure({
    heading: { levels: [1, 2, 3] },
  }),
  Link.configure({
    openOnClick: false,
    HTMLAttributes: { class: "text-blue-600 underline" },
  }),
  Image.configure({
    HTMLAttributes: { class: "max-w-full rounded-lg" },
  }),
  Placeholder.configure({ placeholder: "Начните писать..." }),
  TextAlign.configure({
    types: ["heading", "paragraph"],
  }),
  Underline,
  Highlight.configure({
    HTMLAttributes: { class: "bg-yellow-200" },
  }),
];
```

### 6.3. Компонент `RichTextEditor`

```tsx
"use client";

import { useEditor, EditorContent } from "@tiptap/react";
import DOMPurify from "dompurify";
import { useRef, useEffect } from "react";

const SANITIZE_CONFIG = {
  ALLOWED_TAGS: [
    "p", "br", "strong", "b", "em", "i", "u", "s",
    "h1", "h2", "h3",
    "ul", "ol", "li",
    "a", "img",
    "blockquote", "pre", "code",
    "div", "span", "mark", "hr",
  ],
  ALLOWED_ATTR: [
    "href", "src", "alt", "title", "target",
    "class", "style",
  ],
};

function sanitizeHtml(html: string): string {
  if (typeof window === "undefined") return html;
  return DOMPurify.sanitize(html, SANITIZE_CONFIG);
}

interface RichTextEditorProps {
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  label?: string;
  error?: string;
}

export function RichTextEditor({
  value,
  onChange,
  placeholder,
  disabled,
  label,
  error,
}: RichTextEditorProps) {
  const lastEmittedRef = useRef<string | null>(null);

  const editor = useEditor({
    immediatelyRender: false, // для Next.js App Router
    extensions,
    content: value,
    editable: !disabled,
    editorProps: {
      attributes: {
        class: "prose prose-sm max-w-none p-4 min-h-[200px] focus:outline-none",
      },
    },
    onUpdate: ({ editor }) => {
      const html = editor.getHTML();
      const sanitized = sanitizeHtml(html);
      lastEmittedRef.current = sanitized;
      onChange?.(sanitized);
    },
  });

  // Синхронизация с родительским value без сброса курсора
  useEffect(() => {
    if (!editor || !value) return;
    if (value === lastEmittedRef.current) return;
    if (value !== editor.getHTML()) {
      editor.commands.setContent(sanitizeHtml(value), false);
    }
  }, [editor, value]);

  return (
    <div>
      {label && <label className="block text-sm font-medium mb-1">{label}</label>}
      {editor && <MenuBar editor={editor} />}
      <div className="border rounded-lg overflow-hidden">
        <EditorContent editor={editor} />
      </div>
      {error && <p className="text-red-500 text-sm mt-1">{error}</p>}
    </div>
  );
}
```

### 6.4. Тулбар (`MenuBar`)

Кнопки для форматирования:

| Группа | Кнопки |
|--------|--------|
| Текст | Bold, Italic, Underline, Strikethrough, Highlight |
| Заголовки | H1, H2, H3 |
| Списки | Bullet list, Ordered list |
| Выравнивание | Left, Center, Right |
| Вставки | Link, Image (по URL), Blockquote, Code block, Horizontal rule |
| Действия | Undo, Redo |

Каждая кнопка проверяет `editor.isActive(...)` для подсветки активного состояния.

### 6.5. Стили для `.prose` в CSS

Если не используете плагин `@tailwindcss/typography`, добавьте в глобальный CSS:

```css
/* Стили для контента WYSIWYG-редактора и отображения HTML */
.prose h1 { font-size: 1.5rem; font-weight: 700; margin-top: 1.5rem; margin-bottom: 1rem; }
.prose h2 { font-size: 1.25rem; font-weight: 600; margin-top: 1.25rem; margin-bottom: 0.75rem; }
.prose h3 { font-size: 1.1rem; font-weight: 600; margin-top: 1rem; margin-bottom: 0.5rem; }
.prose p { margin-bottom: 0.75rem; line-height: 1.625; }
.prose ul { list-style-type: disc; padding-left: 1.5rem; margin-bottom: 0.75rem; }
.prose ol { list-style-type: decimal; padding-left: 1.5rem; margin-bottom: 0.75rem; }
.prose li { margin-bottom: 0.25rem; }
.prose a { color: #2563eb; text-decoration: underline; }
.prose blockquote {
  border-left: 3px solid #d1d5db;
  padding-left: 1rem;
  font-style: italic;
  color: #6b7280;
  margin: 1rem 0;
}
.prose code { background: #f3f4f6; padding: 0.15rem 0.3rem; border-radius: 0.25rem; font-size: 0.875em; }
.prose pre { background: #1f2937; color: #e5e7eb; padding: 1rem; border-radius: 0.5rem; overflow-x: auto; margin: 1rem 0; }
.prose pre code { background: none; padding: 0; }
.prose img { max-width: 100%; border-radius: 0.5rem; margin: 1rem 0; }
.prose hr { border-color: #e5e7eb; margin: 1.5rem 0; }
.prose mark { background-color: #fef08a; padding: 0.1rem 0.2rem; }
```

### 6.6. Компонент `HtmlContent` для отображения

Для рендера HTML-контента документов на публичной части или в превью:

```tsx
import DOMPurify from "dompurify";

interface HtmlContentProps {
  html: string | null;
  className?: string;
}

export function HtmlContent({ html, className }: HtmlContentProps) {
  if (!html) return null;

  const sanitized =
    typeof window !== "undefined"
      ? DOMPurify.sanitize(html, SANITIZE_CONFIG)
      : html;

  return (
    <div
      className={`prose prose-sm max-w-none ${className ?? ""}`}
      dangerouslySetInnerHTML={{ __html: sanitized }}
    />
  );
}
```

---

## 7. React Query — хуки и ключи

```ts
// --- Ключи ---
export const documentKeys = {
  all: ["documents"] as const,
  lists: () => [...documentKeys.all, "list"] as const,
  list: (params: Record<string, unknown>) => [...documentKeys.lists(), params] as const,
  details: () => [...documentKeys.all, "detail"] as const,
  detail: (id: string) => [...documentKeys.details(), id] as const,
};

// --- Хуки ---

// Список
function useDocuments(params: { status?: string; search?: string; cursor?: string }) {
  return useQuery({
    queryKey: documentKeys.list(params),
    queryFn: () => api.get("/api/v1/admin/documents", { params }),
  });
}

// Деталь
function useDocument(id: string) {
  return useQuery({
    queryKey: documentKeys.detail(id),
    queryFn: () => api.get(`/api/v1/admin/documents/${id}`),
    enabled: !!id,
  });
}

// Создание
function useCreateDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: DocumentCreateRequest) =>
      api.post("/api/v1/admin/documents", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
    },
  });
}

// Обновление
function useUpdateDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: DocumentUpdateRequest }) =>
      api.patch(`/api/v1/admin/documents/${id}`, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
      queryClient.invalidateQueries({ queryKey: documentKeys.detail(id) });
    },
  });
}

// Удаление
function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/v1/admin/documents/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
    },
  });
}

// Публикация / снятие
function usePublishDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post(`/api/v1/admin/documents/${id}/publish`),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
      queryClient.invalidateQueries({ queryKey: documentKeys.detail(id) });
    },
  });
}

function useUnpublishDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post(`/api/v1/admin/documents/${id}/unpublish`),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
      queryClient.invalidateQueries({ queryKey: documentKeys.detail(id) });
    },
  });
}

// Файл
function useUploadDocumentFile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => {
      const formData = new FormData();
      formData.append("file", file);
      return api.post(`/api/v1/admin/documents/${id}/file`, formData);
    },
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.detail(id) });
    },
  });
}

function useDeleteDocumentFile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.delete(`/api/v1/admin/documents/${id}/file`),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.detail(id) });
    },
  });
}
```

---

## 8. Рекомендуемая файловая структура на фронте

```
src/
├── entities/document/
│   └── types.ts                    # Document, DocumentCreateRequest, DocumentUpdateRequest
├── features/documents/
│   ├── api/
│   │   ├── documentsApi.ts         # HTTP-вызовы
│   │   └── documentKeys.ts         # React Query ключи
│   ├── model/
│   │   └── useDocuments.ts         # Хуки: useDocuments, useCreateDocument, ...
│   └── ui/
│       ├── DocumentsTable.tsx      # Таблица списка
│       ├── DocumentForm.tsx        # Форма создания/редактирования
│       ├── DocumentStatusBadge.tsx # Бейдж статуса
│       └── DocumentFileUpload.tsx  # Блок загрузки файла
├── shared/ui/
│   ├── RichTextEditor/
│   │   ├── RichTextEditor.tsx      # WYSIWYG (TipTap)
│   │   └── index.ts
│   └── HtmlContent/
│       ├── HtmlContent.tsx         # Рендер HTML
│       └── index.ts
└── app/(dashboard)/documents/
    ├── page.tsx                    # Страница списка
    └── [id]/
        └── page.tsx                # Страница редактирования
```

---

## 9. Чеклист реализации

1. **Типы** — `Document`, `DocumentCreateRequest`, `DocumentUpdateRequest`
2. **API-клиент** — CRUD + publish/unpublish + file upload/delete
3. **React Query хуки** — с инвалидацией кешей
4. **Страница списка** — таблица, фильтр по статусу, поиск, курсорная пагинация
5. **Форма** — все поля, автогенерация slug, RichTextEditor для `content`
6. **Optimistic locking** — передавать `version`, обрабатывать `VERSION_CONFLICT`
7. **Загрузка файла** — отдельный блок, только после создания документа
8. **Бейдж статуса** — draft=серый, published=зелёный, archived=жёлтый
9. **WYSIWYG** — TipTap 3 с sanitization через DOMPurify
10. **Стили `.prose`** — в globals.css или через `@tailwindcss/typography`
11. **`HtmlContent`** — для превью и публичного отображения
12. **Навигация** — добавить пункт «Документы» в sidebar админки
