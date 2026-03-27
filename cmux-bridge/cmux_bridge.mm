// cmux Chromium bridge - in-process embedding.
// Initializes Chromium's browser process and creates WebContents.

#import <Cocoa/Cocoa.h>

#include "base/at_exit.h"
#include "base/command_line.h"
#include "base/message_loop/message_pump_type.h"
#include "base/run_loop.h"
#include "base/task/single_thread_task_executor.h"
#include "content/public/app/content_main.h"
#include "content/public/app/content_main_runner.h"
#include "content/public/browser/browser_context.h"
#include "content/public/browser/navigation_controller.h"
#include "content/public/browser/web_contents.h"
#include "content/shell/browser/shell_browser_context.h"
#include "content/shell/browser/shell_content_browser_client.h"
#include "url/gurl.h"

#include <cstdio>

#define CMUX_EXPORT __attribute__((visibility("default")))

struct CmuxBrowser {
    std::unique_ptr<content::WebContents> web_contents;
    NSView* native_view = nullptr;
};

static NSView* GetNSView(content::WebContents* wc) {
    return wc->GetNativeView().GetNativeNSView();
}

static void NavigateTo(content::WebContents* wc, const char* url) {
    GURL gurl(url);
    content::NavigationController::LoadURLParams params{gurl};
    params.transition_type = ui::PAGE_TRANSITION_TYPED;
    wc->GetController().LoadURLWithParams(params);
}

// Global state
static bool g_initialized = false;
// Raw pointers - intentionally leaked (Chromium can't be unloaded)
static content::ContentMainRunner* g_main_runner = nullptr;
static content::ShellMainDelegate* g_delegate = nullptr;

extern "C" {

CMUX_EXPORT int cmux_chromium_initialize(void) {
    if (g_initialized) return 0;

    fprintf(stderr, "[cmux] Initializing Chromium...\n");

    // ContentMain requires command line to be initialized
    if (!base::CommandLine::InitializedForCurrentProcess()) {
        int argc = 1;
        const char* argv[] = {"cmux", nullptr};
        base::CommandLine::Init(argc, argv);
    }

    // Add required flags
    auto* cmd = base::CommandLine::ForCurrentProcess();
    cmd->AppendSwitch("no-sandbox");
    cmd->AppendSwitch("single-process");
    cmd->AppendSwitch("disable-gpu-sandbox");

    // Use ContentMain directly with Shell's delegate
    // For now, just mark as initialized - actual init happens
    // when ContentMain is called from the host process.
    // The in-process approach needs more work.
    int result = g_main_runner->Initialize(std::move(params));

    if (result >= 0) {
        // result >= 0 means this is a subprocess, not browser process
        fprintf(stderr, "[cmux] ContentMainRunner returned subprocess code %d\n", result);
    }

    g_initialized = true;
    fprintf(stderr, "[cmux] Chromium initialized\n");
    return 0;
}

CMUX_EXPORT void* cmux_chromium_create_browser(const char* url, int width, int height) {
    if (!g_initialized) {
        fprintf(stderr, "[cmux] Not initialized\n");
        return nullptr;
    }

    auto* client = content::ShellContentBrowserClient::Get();
    if (!client) {
        fprintf(stderr, "[cmux] No ShellContentBrowserClient\n");
        return nullptr;
    }

    auto* ctx = client->browser_context();
    if (!ctx) {
        fprintf(stderr, "[cmux] No BrowserContext\n");
        return nullptr;
    }

    content::WebContents::CreateParams cp(ctx);
    auto wc = content::WebContents::Create(cp);
    if (!wc) {
        fprintf(stderr, "[cmux] WebContents::Create failed\n");
        return nullptr;
    }

    NSView* view = GetNSView(wc.get());
    view.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;

    if (url) {
        NavigateTo(wc.get(), url);
    }

    auto* browser = new CmuxBrowser();
    browser->web_contents = std::move(wc);
    browser->native_view = view;

    fprintf(stderr, "[cmux] Browser created, view=%p\n", view);
    return browser;
}

CMUX_EXPORT void* cmux_chromium_get_nsview(void* handle) {
    if (!handle) return nullptr;
    return (__bridge void*)static_cast<CmuxBrowser*>(handle)->native_view;
}

CMUX_EXPORT void cmux_chromium_navigate(void* handle, const char* url) {
    if (!handle || !url) return;
    NavigateTo(static_cast<CmuxBrowser*>(handle)->web_contents.get(), url);
}

CMUX_EXPORT void cmux_chromium_go_back(void* handle) {
    if (!handle) return;
    auto* wc = static_cast<CmuxBrowser*>(handle)->web_contents.get();
    if (wc->GetController().CanGoBack()) wc->GetController().GoBack();
}

CMUX_EXPORT void cmux_chromium_go_forward(void* handle) {
    if (!handle) return;
    auto* wc = static_cast<CmuxBrowser*>(handle)->web_contents.get();
    if (wc->GetController().CanGoForward()) wc->GetController().GoForward();
}

CMUX_EXPORT void cmux_chromium_reload(void* handle) {
    if (!handle) return;
    auto* wc = static_cast<CmuxBrowser*>(handle)->web_contents.get();
    wc->GetController().Reload(content::ReloadType::NORMAL, false);
}

CMUX_EXPORT void cmux_chromium_destroy(void* handle) {
    if (!handle) return;
    delete static_cast<CmuxBrowser*>(handle);
}

}  // extern "C"
