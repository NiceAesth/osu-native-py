using System.Collections;
using System.Reflection;
using System.Text.Json;
using NUnit.Framework;

var assembly = Assembly.Load("osu.Native.Tests");
var rulesets = new Dictionary<string, int>
{
    ["Osu"] = 0,
    ["Taiko"] = 1,
    ["Catch"] = 2,
    ["Mania"] = 3
};
var cases = new List<object>();

foreach (var type in assembly.GetTypes().OrderBy(type => type.FullName))
{
    var method = type.GetMethod("Calculate_Success");
    if (method is null)
        continue;

    foreach (var source in method.GetCustomAttributes<TestCaseSourceAttribute>())
    {
        var provider = (source.SourceType ?? type).GetMethod(
            source.SourceName!, BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic)!;
        foreach (TestCaseData test in (IEnumerable)provider.Invoke(null, source.MethodParams)!)
        {
            var arguments = test.Arguments;
            var attributes = arguments[^1]!;
            var name = attributes.GetType().Name["Native".Length..];
            var mode = rulesets.Single(pair => name.StartsWith(pair.Key)).Value;
            cases.Add(new
            {
                ruleset = mode,
                beatmap = arguments[0],
                mods = arguments[1],
                score = arguments.Length == 4 ? Fields(arguments[2]!) : null,
                attributes = name,
                expected = Fields(attributes)
            });
        }
    }
}

if (cases.Count == 0)
    throw new InvalidOperationException("No upstream calculator test cases found.");

File.WriteAllText(args[0], JsonSerializer.Serialize(cases));

static Dictionary<string, object?> Fields(object value) => value.GetType().GetFields()
    .Where(field => !field.Name.EndsWith("Handle"))
    .ToDictionary(field => JsonNamingPolicy.SnakeCaseLower.ConvertName(field.Name), field => field.GetValue(value));
