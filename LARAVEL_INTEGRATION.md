# Integrasi Laravel dengan AI API

Panduan untuk mengintegrasikan API FastAPI ke aplikasi Laravel.

## 📦 Instalasi di Laravel

### 1. Install HTTP Client (Guzzle sudah include di Laravel)
Tidak perlu install tambahan, Laravel sudah include Guzzle HTTP Client.

### 2. Buat Service Class

Buat file `app/Services/AiApiService.php`:

```php
<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class AiApiService
{
    protected string $baseUrl;
    protected int $timeout;

    public function __construct()
    {
        $this->baseUrl = config('services.ai_api.url', 'http://localhost:8000');
        $this->timeout = config('services.ai_api.timeout', 300); // 5 menit untuk upload PDF
    }

    /**
     * Upload PDF ke AI API (Admin)
     */
    public function uploadPdf($filePath, $fileName = null): array
    {
        try {
            $response = Http::timeout($this->timeout)
                ->attach('file', file_get_contents($filePath), $fileName ?? basename($filePath))
                ->post("{$this->baseUrl}/admin/upload");

            if ($response->successful()) {
                return [
                    'success' => true,
                    'data' => $response->json(),
                    'message' => 'PDF berhasil diupload'
                ];
            }

            return [
                'success' => false,
                'message' => $response->json()['detail'] ?? 'Upload gagal',
                'errors' => $response->json()
            ];
        } catch (\Exception $e) {
            Log::error('AI API Upload Error: ' . $e->getMessage());
            return [
                'success' => false,
                'message' => 'Terjadi kesalahan saat upload: ' . $e->getMessage()
            ];
        }
    }

    /**
     * Cek status index (Admin)
     */
    public function getStatus(): array
    {
        try {
            $response = Http::timeout(10)
                ->get("{$this->baseUrl}/admin/status");

            if ($response->successful()) {
                return [
                    'success' => true,
                    'data' => $response->json()
                ];
            }

            return [
                'success' => false,
                'message' => 'Gagal mengambil status'
            ];
        } catch (\Exception $e) {
            Log::error('AI API Status Error: ' . $e->getMessage());
            return [
                'success' => false,
                'message' => 'Terjadi kesalahan: ' . $e->getMessage()
            ];
        }
    }

    /**
     * Chat dengan AI (User)
     */
    public function chat(string $question): array
    {
        try {
            $response = Http::timeout(60)
                ->post("{$this->baseUrl}/chat", [
                    'question' => $question
                ]);

            if ($response->successful()) {
                return [
                    'success' => true,
                    'data' => $response->json()
                ];
            }

            $errorDetail = $response->json()['detail'] ?? 'Chat gagal';
            return [
                'success' => false,
                'message' => is_string($errorDetail) ? $errorDetail : json_encode($errorDetail),
                'errors' => $response->json()
            ];
        } catch (\Exception $e) {
            Log::error('AI API Chat Error: ' . $e->getMessage());
            return [
                'success' => false,
                'message' => 'Terjadi kesalahan saat chat: ' . $e->getMessage()
            ];
        }
    }

    /**
     * Health check
     */
    public function healthCheck(): bool
    {
        try {
            $response = Http::timeout(5)->get("{$this->baseUrl}/health");
            return $response->successful() && $response->json()['status'] === 'ok';
        } catch (\Exception $e) {
            return false;
        }
    }
}
```

### 3. Konfigurasi Services

Edit `config/services.php`:

```php
return [
    // ... existing configs ...

    'ai_api' => [
        'url' => env('AI_API_URL', 'http://localhost:8000'),
        'timeout' => env('AI_API_TIMEOUT', 300),
    ],
];
```

### 4. Environment Variables

Edit `.env`:

```env
AI_API_URL=http://localhost:8000
# Atau jika di server:
# AI_API_URL=http://your-server-ip:8000
# AI_API_URL=https://api-umkm-ai.example.com

AI_API_TIMEOUT=300
```

### 5. Buat Controller Admin

Buat `app/Http/Controllers/Admin/AiController.php`:

```php
<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Services\AiApiService;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Storage;

class AiController extends Controller
{
    protected AiApiService $aiService;

    public function __construct(AiApiService $aiService)
    {
        $this->aiService = $aiService;
    }

    /**
     * Upload PDF
     */
    public function uploadPdf(Request $request)
    {
        $request->validate([
            'file' => 'required|file|mimes:pdf|max:10240', // Max 10MB
        ]);

        $file = $request->file('file');
        $filePath = $file->getRealPath();
        
        $result = $this->aiService->uploadPdf($filePath, $file->getClientOriginalName());

        if ($result['success']) {
            return response()->json([
                'success' => true,
                'message' => $result['message'],
                'data' => $result['data']
            ], 200);
        }

        return response()->json([
            'success' => false,
            'message' => $result['message']
        ], 400);
    }

    /**
     * Get status
     */
    public function getStatus()
    {
        $result = $this->aiService->getStatus();

        if ($result['success']) {
            return response()->json($result['data'], 200);
        }

        return response()->json([
            'message' => $result['message']
        ], 500);
    }
}
```

### 6. Buat Controller User

Buat `app/Http/Controllers/ChatController.php`:

```php
<?php

namespace App\Http\Controllers;

use App\Services\AiApiService;
use Illuminate\Http\Request;

class ChatController extends Controller
{
    protected AiApiService $aiService;

    public function __construct(AiApiService $aiService)
    {
        $this->aiService = $aiService;
    }

    /**
     * Chat dengan AI
     */
    public function chat(Request $request)
    {
        $request->validate([
            'question' => 'required|string|max:1000',
        ]);

        $result = $this->aiService->chat($request->question);

        if ($result['success']) {
            return response()->json([
                'success' => true,
                'data' => $result['data']
            ], 200);
        }

        return response()->json([
            'success' => false,
            'message' => $result['message']
        ], 400);
    }
}
```

### 7. Routes

Edit `routes/api.php`:

```php
use App\Http\Controllers\ChatController;
use App\Http\Controllers\Admin\AiController;

// User routes
Route::prefix('chat')->group(function () {
    Route::post('/', [ChatController::class, 'chat']);
});

// Admin routes (pakai middleware auth jika perlu)
Route::prefix('admin/ai')->middleware(['auth:sanctum'])->group(function () {
    Route::post('/upload', [AiController::class, 'uploadPdf']);
    Route::get('/status', [AiController::class, 'getStatus']);
});
```

Atau di `routes/web.php` untuk web routes:

```php
// Admin routes
Route::middleware(['auth'])->prefix('admin/ai')->group(function () {
    Route::post('/upload', [App\Http\Controllers\Admin\AiController::class, 'uploadPdf']);
    Route::get('/status', [App\Http\Controllers\Admin\AiController::class, 'getStatus']);
});

// User routes
Route::post('/chat', [App\Http\Controllers\ChatController::class, 'chat']);
```

## 📝 Contoh Penggunaan di Blade/View

```blade
<!-- Upload PDF -->
<form id="uploadForm" enctype="multipart/form-data">
    @csrf
    <input type="file" name="file" accept=".pdf" required>
    <button type="submit">Upload PDF</button>
</form>

<script>
document.getElementById('uploadForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    const formData = new FormData(this);
    
    const response = await fetch('/admin/ai/upload', {
        method: 'POST',
        body: formData,
        headers: {
            'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content
        }
    });
    
    const result = await response.json();
    alert(result.message);
});
</script>
```

## 🔒 Security Tips

1. **Gunakan Middleware Auth** untuk admin routes
2. **Rate Limiting** untuk chat endpoint
3. **Validasi file** di Laravel (size, type)
4. **Sanitize input** sebelum kirim ke API
5. **Gunakan HTTPS** di production

## 🧪 Testing

```php
// tests/Feature/AiApiTest.php
use Tests\TestCase;
use App\Services\AiApiService;

class AiApiTest extends TestCase
{
    public function test_health_check()
    {
        $service = new AiApiService();
        $this->assertTrue($service->healthCheck());
    }

    public function test_chat()
    {
        $service = new AiApiService();
        $result = $service->chat('Apa itu UMKM?');
        
        $this->assertTrue($result['success']);
        $this->assertArrayHasKey('data', $result);
    }
}
```

## 📊 Error Handling

Pastikan handle error dengan baik:

```php
try {
    $result = $aiService->chat($question);
    if (!$result['success']) {
        // Handle error
        Log::warning('AI API Error', ['result' => $result]);
    }
} catch (\Exception $e) {
    Log::error('AI API Exception', ['error' => $e->getMessage()]);
}
```


