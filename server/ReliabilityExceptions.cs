namespace VideoStudio.Server;

public sealed class IdempotencyConflictException : InvalidOperationException
{
    public IdempotencyConflictException(string message) : base(message) { }
}

public sealed class StaleTaskLeaseException : InvalidOperationException
{
    public StaleTaskLeaseException(string message) : base(message) { }
}
