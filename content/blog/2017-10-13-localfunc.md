Title: Lambdas and Local Functions
Slug: localfunc

Ever since local functions were added in C# 7 a common user question has
been, "when should I use them instead of a lambda?" They're both forms of
functions that can be nested within other functions, so it's reasonable to
ask what the difference is. First, it's probably useful to say when *can* you
use them instead of a lambda. The answer is: wherever you can define a
statement, you can use a local function instead of a lambda. Basically, if
there's a pair of curly braces, you can use a local function instead of a
lambda. The only thing that a lambda can do that a local function cannot is
be defined in an expression context (like a field initializer).[^1]

So now that we've covered where you *can* use local functions instead of
lambdas, that leaves the question of where you *should*. This is somewhat
of a personal style question, but I can give you some situations where
local functions can do things that lambdas can't. The most obvious of these
is that local functions can have names, while lambdas can't. In fact,
the spec also uses the words "anonymous function" to refer to lambda methods.
Similarly, the term "lambda" (referring to the symbol λ), is what Alonzo
Church used to represent anonymous functions when he invented them.

That means that if you're currently writing code like

```csharp
void Method(string str)
{
    Func<string, int> myFunc = s => int.TryParse(s);

    if (myFunc(str))
    ...
}
```

you should consider rewriting it into something like

```csharp
void Method(string str)
{
    int MyFunc(string s) => int.TryParse(s);

    if (MyFunc(s))
    ...
}
```

If nothing else, you might find this more readable due to the parameter types
being right next to the parameter names. In case that's not enough, here's
a list of things that local functions can do that lambdas can't:

* Local functions can be called without converting to a delegate, so you don't
  need to wrap them in `Func` or `Action` if you're just calling from your
  current method

* Local functions can be recursive[^2]

* Local functions can be iterators
    - Since iterators don't start running until you start iterating over them
        this can be very useful if you want to do a little early-validation for
        your iterator method. You can stick the body of your iterator in a local
        function, do your validation up front, and then call your iterator.

* Local functions can be generic (e.g., `bool Local<T>(T t) => t == default(T);`)

* Local functions have strictly more precise definite assignment rules

* In certain cases, local functions do not need to allocate memory on the heap


Those last two points are pretty complicated, so let me explain in more
detail. First, definite assignment. Definite assignment is the rule that in
C#, all variables must definitely be assigned before they can be used. This
is the actual reason that lambdas cannot be recursive; the lambda is defined
before it is assigned to the delegate, so the delegate variable cannot be
used in the body of the lambda until it's been assigned. This is why

```csharp
Action a = () => a();
```

produces the error, `Use of unassigned local variable 'a'`, while

```csharp
Action a = null; 
a = () => a();
```

compiles without issue.

However, there's more to just definite assignment then just the variable the
local function is assigned to. There's also the matter of captured variables.
Variables captured within lambdas are required to be definitely assigned
whenever a lambda is used. Lambdas are considered used when they are converted
to delegates[^3], so all captured variables must be definitely assigned at
the lambda declaration point. On the other hand, while local functions also
require captured variables to be assigned when they're converted to delegates,
local function declarations aren't considered usage. This allows you to do things
like define your local functions at the end of the method, even after `return`
statements, and the assignment rules will only be enforced at the usage point.
For example,

```csharp
Func<bool> M()
{
    int y;
    Func<bool> eqZ = () => y == 0; // Lambda: Illegal, y hasn't been assigned yet

    bool EqZ() => y == 0; // Local Function: Perfectly fine, just the definition

    y = 0;
    return EqZ; // y is assigned at the delegate conversion, so it's all good
}
```

If you don't convert the local function to a delegate, but instead just call
it like a method, things get even fancier. Unlike lambdas, local functions
can also definitely assign captured variables in their enclosing method scope.

```csharp
bool M()
{
    int y;
    Local();
    return y;

    void Local() => y = 0;
}
```

This is all a consequence of the fact that the compiler can "see through" calls
to local functions in the current method. This means they can have complex
definite assignment across calls, but also that their compilation can be more
advanced in general.

The most notable use of the extra information is avoiding heap allocation
when 1) the local function is not converted to a delegate and 2) none of the
variables it captures are captured by lambdas or local functions converted to
delegates.[^4] For example, if you take existing lambda code

```csharp
bool M(int x)
{
    foreach (var c in myCollection)
    {
        // Pretend this helper does something complex
        Func<bool> helper = () => IsValid(c, x);
        if (helper())
        {
            break;
        }
        ...
    }
    ...
}
```

and rewrite it to

```csharp
bool M(int x)
{
    foreach (var c in myCollection)
    {
        bool Helper() => IsValid(c, x);
        if (Helper())
        {
            break;
        }
        ...
    }
    ...
}
```

then the classes previously allocated to hold the captured variables `x`
and `c` will instead be replaced by structs and then passed by ref to the
synthesized function used to represent `Helper`. This will save an extra
class allocation for each iteration of this loop, since a new `c` is
captured on every iteration. This is all stack allocation, so no garbage will
be created for the GC to collect and your program may run a bit faster.

Unfortunately, if you're thinking of using this for LINQ to avoid allocation,
calling LINQ methods always requires passing a delegate, which will force
allocation anyway. However, if you're looking to create helper methods and
were afraid of using lambdas due to performance concerns, this may help
significantly.

So, to sum up, there's no hard and fast rule when you should use a local function
instead of a lambda, or vice versa, but if you find one of the previous
situations applies to you, or you just like the look of local functions better,
you might give local functions a try.


[^1]: A clever C# user may say, "what about expression trees? Local functions
 can't be converted to expression trees!". True, but a lambda can't be
 converted to an expression tree either&mdash;expression trees are defined
 using lambda *syntax*, they aren't themselves lambdas.

[^2]: OK, fine, here's the *Y* combinator, go crazy:

        using System;
        public class C 
        {
            delegate Func<T, T2> Rec<T, T2>(Rec<T, T2> f);

            public static Func<T, T2> Y<T, T2>(Func<Func<T, T2>, Func<T, T2>> f)
                => new Rec<T, T2>(
                    x => h => f(x(x))(h))(
                    x => h => f(x(x))(h));
        }

[^3]: This is because the flow of delegates isn't tracked by the compiler.
Since delegates can be passed in and out of external functions, even external
assemblies, there's no safe way to fully track delegates, so the compiler
enforces all the rules at the point of delegate conversion.

[^4]: All lambdas must be converted to delegates, so you can see why this
optimization can only be performed for local functions.