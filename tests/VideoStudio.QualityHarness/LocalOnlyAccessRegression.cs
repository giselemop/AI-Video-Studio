using System.Net;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging.Abstractions;
using VideoStudio.Server;

internal static class LocalOnlyAccessRegression
{
    public static async Task Run()
    {
        var settings = new StudioSettings { RequireLocalLogin = false };
        LocalAuthService Service(StudioSettings config)
        {
            var db = new StudioDb(config, NullLogger<StudioDb>.Instance);
            var repo = new StudioRepository(db, NullLogger<StudioRepository>.Instance);
            return new LocalAuthService(config, repo, NullLogger<LocalAuthService>.Instance);
        }
        DefaultHttpContext Context(string remote = "127.0.0.1", string host = "127.0.0.1:18080", string? origin = null)
        {
            var context = new DefaultHttpContext();
            context.Connection.RemoteIpAddress = IPAddress.Parse(remote);
            context.Request.Host = new HostString(host);
            if (origin is not null) context.Request.Headers.Origin = origin;
            return context;
        }
        var service = Service(settings);
        var checks = 0;
        void Check(bool condition) { if (!condition) throw new Exception("Local-only access regression failed"); checks++; }
        var status = await service.StatusAsync(Context());
        Check(!status.LoginRequired && !status.Authenticated && status.AccessMode == "LocalOnly" && status.CsrfToken is not null);
        Check((await service.AuthenticateAsync(Context(), false)).Allowed);
        Check((await service.AuthenticateAsync(Context(), false)).Principal?.Role == "LocalOperator");
        Check(!(await service.AuthenticateAsync(Context(), true)).Allowed);
        Check(!(await service.AuthenticateAsync(Context("192.168.1.20"), false)).Allowed);
        Check(!(await service.AuthenticateAsync(Context(host: "attacker.example:18080"), false)).Allowed);
        Check(!(await service.AuthenticateAsync(Context(origin: "https://attacker.example"), false)).Allowed);
        Check(!(await service.AuthenticateAsync(Context(origin: "null"), false)).Allowed);
        Check((await service.AuthenticateAsync(Context(host: "localhost:18080", origin: "http://localhost:18080"), false)).Allowed);
        var write = Context(origin: "http://127.0.0.1:18080");
        write.Request.Headers[LocalAuthService.CsrfHeaderName] = status.CsrfToken;
        Check(!(await service.AuthenticateAsync(write, true)).Allowed);
        write.Request.Headers.Cookie = $"{LocalAuthService.CsrfCookieName}={status.CsrfToken}";
        Check((await service.AuthenticateAsync(write, true)).Allowed);
        var otherStatus = await service.StatusAsync(Context());
        Check(otherStatus.CsrfToken != status.CsrfToken && (await service.AuthenticateAsync(write, true)).Allowed);
        var forged = status.CsrfToken![..^1] + (status.CsrfToken[^1] == '0' ? '1' : '0');
        write.Request.Headers[LocalAuthService.CsrfHeaderName] = forged;
        write.Request.Headers.Cookie = $"{LocalAuthService.CsrfCookieName}={forged}";
        Check(!(await service.AuthenticateAsync(write, true)).Allowed);
        write.Request.Headers[LocalAuthService.CsrfHeaderName] = status.CsrfToken;
        write.Request.Headers.Cookie = $"{LocalAuthService.CsrfCookieName}={status.CsrfToken}";
        Check(!(await Service(settings).AuthenticateAsync(write, true)).Allowed);
        Check(!(await service.LoginAsync(Context(), new LocalLoginInput())).Succeeded);
        var protectedService = Service(new StudioSettings { RequireLocalLogin = true, AdminUsername = "fixture-admin", AdminPassword = "test-fixture-only-password" });
        Check((await protectedService.AuthenticateAsync(Context(), false)).StatusCode == 401);
        Console.WriteLine($"Local-only access: {checks} Passed; loopback/host/origin/signed-CSRF and password-mode fallback; no database calls");
    }
}
