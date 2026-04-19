from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def sort_url(context, field):
    """Return a query string that toggles sort direction for the given field.

    If the current sort is already ascending on this field, the returned URL
    will sort descending (prefixed with '-'), and vice versa.
    """
    request = context['request']
    params = request.GET.copy()
    current_sort = params.get('sort', 'created_at')
    if current_sort == field:
        params['sort'] = f'-{field}'
    else:
        params['sort'] = field
    return '?' + params.urlencode()


@register.simple_tag(takes_context=True)
def sort_direction(context, field):
    """Return 'asc', 'desc', or '' for the given sort field."""
    current_sort = context['request'].GET.get('sort', 'created_at')
    if current_sort == field:
        return 'asc'
    if current_sort == f'-{field}':
        return 'desc'
    return ''
