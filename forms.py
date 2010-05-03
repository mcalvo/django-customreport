import copy

from django import forms
from django.db.models.query import QuerySet

from django.contrib.admin.widgets import FilteredSelectMultiple
from django_customreport.helpers import filter_choice_generator

class BaseCustomPreForm(forms.Form):
	def __init__(self,*args,**kwargs):
		self.queryset = kwargs.pop('queryset')
		super(BaseCustomPreForm,self).__init__(*args,**kwargs)

class RelationMultipleChoiceField(forms.MultipleChoiceField):
	def __init__(self,queryset,depth=3,inclusions=None,exclusions=None,filter_fields=None,*args,**kwargs):
		from django_customreport.helpers import display_list
		filter_fields = filter_fields or []
		unfiltered_choices = display_list(queryset,depth=depth,inclusions=inclusions,exclusions=exclusions)
		choices = filter_choice_generator(unfiltered_choices,queryset,filter_fields)

		kwargs.update({
			'choices': choices,
			'widget': FilteredSelectMultiple("display_fields", is_stacked=False)
		})
		super(RelationMultipleChoiceField,self).__init__(*args,**kwargs)

class QueryForm(forms.Form):
	def __init__(self,queryset,inclusions=None,exclusions=None,depth=3,filter_fields=None,*args,**kwargs):
		super(QueryForm,self).__init__(*args,**kwargs)
		self.fields['filter_fields'] = forms.CharField(initial=",".join(filter_fields),\
				widget=forms.widgets.HiddenInput)
		self.fields['display_fields'] = RelationMultipleChoiceField(queryset=\
				queryset,depth=depth,exclusions=exclusions,\
				inclusions=inclusions,filter_fields=filter_fields,\
				required=False,label="Additional display fields")

		if modules:
			self.fields['custom_modules'] = forms.CharField(choices=modules.keys(),required=False)


class FilterSetCustomPreForm(BaseCustomPreForm): # Convenience PreForm which accepts a django-filters filterset
	def __init__(self,filter,data,exclusions=None,inclusions=None,depth=None,queryset=None):
		self._filter = filter
		self._exclusions = exclusions
		self._inclusions = inclusions
		self._depth = depth
		if not isinstance(queryset,QuerySet):
			queryset = filter.queryset

		super(FilterSetCustomPreForm,self).__init__(data,queryset=queryset)
		self.update_field_labels() # Separated in case __init__ work wants to change these labels.

	def update_field_labels(self):
		filter_choices = []
		for field, obj in self._filter.base_filters.iteritems():
			value = field
			if '__' in field:
				value = ' :: '.join(field.split('__')[-2:])
			value = ' '.join(value.split('_'))
			filter_choices.append((field,value.title()))

		import operator
		filter_choices = sorted(filter_choices, key=operator.itemgetter(1))

		self.fields['filter_fields'] = forms.MultipleChoiceField(choices=filter_choices,\
				widget=FilteredSelectMultiple("filter_fields", is_stacked=False))
